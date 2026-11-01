"""BPM text on owned camera frames; original browser owns all four curves."""
from functools import partial
import time

import numpy as np

if __package__:
    from . import video_motion_joint
    from .video_motion_joint import MotionBinding, MotionResources
    from .shadow_joint import TappedMailbox
    from .joint_startup import replace_attribute
else:
    import video_motion_joint
    from video_motion_joint import MotionBinding, MotionResources
    from shadow_joint import TappedMailbox
    from joint_startup import replace_attribute


class HybridMailbox(TappedMailbox):
    def __init__(self,*args,model,**kwargs):
        super().__init__(*args,**kwargs)
        self.model=model

    def publish(self,snapshot):
        observed=self.clock_ns()
        result=super().publish(snapshot)
        self.model.observe(snapshot,published_ns=observed)
        return result


class HybridRaster:
    """One small cached RAM strip, outside the unchanged 320x240 motion ROI."""
    def __init__(self,cv):
        self.cv=cv
        self.strip=np.zeros((72,640,4),np.uint8)
        self.key=None
        self.builds=0

    def paint(self,frame,panel):
        key=(panel['bpm_text'],panel['route'],panel['state'])
        if key!=self.key:
            self.strip[:]=(18,18,18,0)
            color=(70,245,130,0) if panel['eligible'] else (130,180,245,0)
            self.cv.putText(self.strip,'HR '+key[0]+' bpm',(12,31),
                self.cv.FONT_HERSHEY_SIMPLEX,.85,color,2)
            self.cv.putText(self.strip,'ROUTE '+key[1]+' | '+key[2],(12,59),
                self.cv.FONT_HERSHEY_SIMPLEX,.5,(230,230,230,0),1)
            self.key=key
            self.builds+=1
        frame[408:480,:,:]=self.strip
        return dict(layout='camera_bpm_strip_v1',hdmi_curve_count=0,browser_graphics_enabled=True,
            bpm_text=panel['bpm_text'],route=panel['route'],state=panel['state'],eligible=panel['eligible'],
            historical=panel['historical'],sequence=panel['sequence'],source_read_ns=panel['read_ns'],
            generation=panel['generation'])

    def report(self):
        return dict(buffer_bytes=self.strip.nbytes,raster_builds=self.builds,
            full_frame_copies=0,thumbnail_resizes=0,hdmi_curve_count=0)


class _TextHdmi:
    def __init__(self,original,resource):
        self.original,self.resource=original,resource

    def __getattr__(self,name):
        return getattr(self.original,name)

    def writeframe(self,frame):
        r=self.resource
        if r.formal_epoch is None:return self.original.writeframe(frame)
        started=time.perf_counter_ns()
        panel=r.model.panel(r.motion_clock(),curves=False)
        info=r.raster.paint(frame,panel)
        checked=r.motion_clock()
        current=r.model.panel(checked,curves=False)
        revoke=bool(panel['eligible'] and (not current['eligible']
            or current['generation']!=panel['generation']
            or not 0<=checked-panel['read_ns']<=1_000_000_000))
        if revoke:
            current.update(bpm_text='N/A',eligible=False)
            info=r.raster.paint(frame,current)
        info.update(checked_ns=checked,status_age_ns=current['status_age_ns'],
            result_age_ns=None if info['source_read_ns'] is None else checked-info['source_read_ns'],
            revoked_during_render=revoke,render_ns=time.perf_counter_ns()-started)
        self.original.writeframe(frame)
        r.last=info
        r.text_submitted+=1
        r.text_total_ns+=info['render_ns']
        r.text_max_ns=max(r.text_max_ns,info['render_ns'])


class HybridResources(MotionResources):
    def __init__(self,*args,model,**kwargs):
        super().__init__(*args,**kwargs)
        self.model=model
        self.last=None
        self.text_submitted=self.text_total_ns=self.text_max_ns=0

    def open(self):
        identity=super().open()
        self.raster=HybridRaster(self.api.cv2)
        self.hdmi=_TextHdmi(self.hdmi,self)
        return dict(identity,hdmi_layout='camera_bpm_strip_v1',browser_graphics_enabled=True,
            full_resolution_motion_input_unchanged=True,hdmi_curve_count=0)

    def process_ready_frame(self,raw,*,sequence,timestamp_ns):
        self.last=None
        row=super().process_ready_frame(raw,sequence=sequence,timestamp_ns=timestamp_ns)
        if self.last is None:raise RuntimeError('HDMI text submission not recorded')
        return dict(row,hybrid=self.last)

    def hybrid_report(self):
        return dict(submitted_frames=self.text_submitted,
            render_mean_ns=self.text_total_ns/self.text_submitted if self.text_submitted else None,
            render_max_ns=self.text_max_ns,raster=self.raster.report() if hasattr(self,'raster') else None,
            browser_graphics_enabled=True,scope='submitted text/source audit; physical display not measured')


class HybridBinding(MotionBinding):
    def __init__(self,*args,model,**kwargs):
        self.model=model
        super().__init__(*args,**kwargs)

    def prepare(self,*args,**kwargs):
        with replace_attribute(video_motion_joint,'MotionResources',partial(HybridResources,model=self.model)):
            session=super().prepare(*args,**kwargs)
        session._preflight.update(hybrid_display=True,browser_graphics_enabled=True,hdmi_curve_count=0)
        return session

    def report(self):
        return dict(super().report(),hybrid_display=self.video.hybrid_report() if self.video else None)
