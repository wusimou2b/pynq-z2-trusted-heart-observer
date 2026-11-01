"""Raw USB input -> PL color + ROI + frame writeback -> existing HDMI channel."""
import time

import numpy as np

if __package__:
    from .joint_video_runtime import load_board_api,STAT_FIELDS
    from .joint_video_transport import DeadlineMMIO
    from .yuyv_owner import YuyvOwner
    from .yuyv_transport import YuyvPort
    from .yuyv_reference import validate_yuyv,yuyv_to_bgr_q20
    from ..vision_reference import VisionReference
else:
    from joint_video_runtime import load_board_api,STAT_FIELDS
    from joint_video_transport import DeadlineMMIO
    from yuyv_owner import YuyvOwner
    from yuyv_transport import YuyvPort
    from yuyv_reference import validate_yuyv,yuyv_to_bgr_q20
    from vision_reference import VisionReference


def load_api():
    api=load_board_api()
    from pynq.lib.video.common import PixelFormat,PIXEL_BGR
    api.PixelFormat,api.PIXEL_BGR=PixelFormat,PIXEL_BGR
    return api


class Resources:
    def __init__(self,directory,*,cancelled,on_event,api_factory=load_api,owner_factory=YuyvOwner):
        self.directory,self.cancelled,self.on_event=directory,cancelled,on_event
        self.api_factory,self.owner_factory=api_factory,owner_factory
        self.owner=self.api=self.camera=self.hdmi=self.vdma=self.guard=None
        self.input=self.pending=self.port=None
        self.stage='new';self.captured=self.submitted=0
        self.retained=[];self.cleanup=None

    def _stage(self,name):self.stage=name;self.on_event({'stage':name,'monotonic_ns':time.monotonic_ns()})
    def _available(self):
        if self.cancelled():raise RuntimeError('user stop requested')
        if self.owner is not None and not self.owner._hardware.is_loaded():raise RuntimeError('YUYV Overlay changed')

    def open(self):
        if self.stage!='new':raise RuntimeError('resources already attempted')
        self._stage('imports');self.api=self.api_factory()
        self.owner=self.owner_factory(self.directory,on_event=self.on_event)
        self._stage('explicit_yuyv_overlay');identity=self.owner.open()
        cv=self.api.cv2
        self._stage('raw_camera_startup');self.camera=cv.VideoCapture('/dev/video0',cv.CAP_V4L2)
        if not self.camera.isOpened():raise RuntimeError('camera open failed; no retry')
        for key,value in ((cv.CAP_PROP_FRAME_WIDTH,640),(cv.CAP_PROP_FRAME_HEIGHT,480),
                          (cv.CAP_PROP_FOURCC,cv.VideoWriter_fourcc(*'YUYV')),(cv.CAP_PROP_CONVERT_RGB,0)):
            if not self.camera.set(key,value):raise RuntimeError('raw camera setting rejected')
        if (self.camera.get(cv.CAP_PROP_FOURCC)!=cv.VideoWriter_fourcc(*'YUYV') or self.camera.get(cv.CAP_PROP_CONVERT_RGB)!=0
            or self.camera.get(cv.CAP_PROP_FRAME_WIDTH)!=640 or self.camera.get(cv.CAP_PROP_FRAME_HEIGHT)!=480):
            raise RuntimeError('raw camera readback mismatch')
        ok,raw=self.camera.read()
        if not ok:raise RuntimeError('raw camera startup read failed')
        validate_yuyv(raw,camera_geometry=True);del raw
        self._stage('hdmi_bgrx_binding')
        view=self.owner._hardware._overlay;self.vdma=view.hdmi_vdma
        if self.vdma.framecount!=4 or hasattr(self.vdma,'readchannel'):raise RuntimeError('four-slot MM2S-only HDMI required')
        channel=self.vdma.writechannel
        channel.cacheable_frames=False
        self.guard=DeadlineMMIO(channel._mmio,is_loaded=self.owner._hardware.is_loaded)
        channel._mmio=self.guard
        if hasattr(channel._frames,'_mmio'):channel._frames._mmio=self.guard
        self.hdmi=self.api.VideoOut(view.hierarchy_dict['hdmi_out'],vdma=self.vdma)
        fmt=self.api.PixelFormat(32,self.api.PIXEL_BGR.in_color,self.api.PIXEL_BGR.out_color)
        with self.guard.budget(5,'configure BGRX32'):
            self.hdmi.configure(self.api.VideoMode(640,480,32,60),pixelformat=fmt)
        with self.guard.budget(3,'start'):self.hdmi.start()
        io=self.owner._io['hdmi_vdma']
        if io.read(0)&2 or io.read(0x54)!=2560 or io.read(0x58)&0xffffff!=2560 or io.read(0x50)!=480:
            raise RuntimeError('BGRX HDMI parking/geometry mismatch')
        self.input=self.api.allocate(shape=(480,640,2),dtype=np.uint8,cacheable=True)
        def display_owned(address):
            frames=channel._frames
            return any(frames[i] is not None and int(frames[i].physical_address)==address for i in range(len(frames)))
        self.port=YuyvPort(self.owner._io['vision_0'],self.owner._io['vision_dma'],self.owner._io['display_dma'],
            self.owner._io['vision_control'],self.owner._io['yuyv_control'],self.input,
            is_loaded=self.owner._hardware.is_loaded,cancelled=self.cancelled,display_owned=display_owned)
        self.port.start();self._stage('ready')
        return {'joint_identity':identity,'raw_camera_format':'YUYV','hdmi_format':'BGRX32',
                'hdmi_stride':2560,'hdmi_cacheable_requested':False,'driver_identity':self.api.driver_identity,
                'cache_policy':'noncoherent frames flush before S2MM, invalidate after; never override coherent flag',
                'same_input_reference_scope':'first two frames after confirmed hardware cleanup',
                'retained_ram_limit_bytes':3686400,'heart_capture_started':False}

    def process_ready_frame(self,raw,*,sequence,timestamp_ns):
        self._available();validate_yuyv(raw,camera_geometry=True);self.captured+=1
        self._stage('new_display_frame');self.pending=self.hdmi.newframe()
        self._stage('pl_color_roi_writeback')
        result=self.port.process(raw,self.pending,sequence=sequence,timestamp_ns=timestamp_ns)
        if self.port.take_completed_frame() is not self.pending:raise RuntimeError('destination ownership changed')
        if len(self.retained)<2:
            self.retained.append((raw.copy(),np.array(self.pending,copy=True),dict(result)))
        cv=self.api.cv2
        self._stage('annotate_written_frame')
        cv.rectangle(self.pending,(160,120),(479,359),(0,255,0,0),1)
        cv.putText(self.pending,'YUYV PL | HEART OFF | seq='+str(sequence),(10,22),
                   cv.FONT_HERSHEY_SIMPLEX,.48,(0,255,255,0),1)
        self._stage('hdmi_submit')
        with self.guard.budget(1,'frame submit'):
            while not int(self.guard.read(4))&0x1000:
                self._available();time.sleep(.001)
            self.hdmi.writeframe(self.pending)
        self.pending=None;self.submitted+=1;self._stage('ready')
        return {'source_sequence':sequence,'read_completed_ns':timestamp_ns,'vision':result,'hdmi_submitted':True}

    def close(self):
        if self.cleanup is not None:return self.cleanup
        result={'cleanup_complete':False,'camera_released':self.camera is None,'hdmi_closed':self.hdmi is None,
                'buffers_released':False,'actual_lease_released':False,'quarantine_required':False,'errors':[]}
        def attempt(stage,fn):
            try:fn();return True
            except BaseException as exc:result['errors'].append({'stage':stage,'type':type(exc).__name__,'message':str(exc)});return False
        if self.camera is not None:result['camera_released']=attempt('camera_release',self.camera.release)
        joint=self.owner.close() if self.owner is not None else {'download_attempts':0,'cleanup_complete':True,'dma':{}}
        result['joint']=joint
        halted=not joint['download_attempts'] or (len(joint['dma'])==3 and all(v.get('halted') for v in joint['dma'].values()))
        if halted and joint['cleanup_complete']:
            if self.hdmi is not None:
                def close_hdmi():
                    with self.guard.budget(3,'close',allow_halted_errors=True):self.hdmi.close()
                result['hdmi_closed']=attempt('hdmi_close',close_hdmi)
            if result['hdmi_closed']:
                def release():
                    if self.port is not None:self.port.active_destination=None
                    if self.pending is not None:self.pending.freebuffer();self.pending=None
                    if self.input is not None:self.input.freebuffer();self.input=None
                    if self.vdma is not None:
                        frames=self.vdma.writechannel._frames
                        with self.guard.budget(2,'release stopped frame cache',allow_halted_errors=True):
                            for i in range(len(frames)):frames[i]=None
                        self.vdma.writechannel._cache.clear()
                result['buffers_released']=attempt('buffers_release',release)
                if result['buffers_released']:
                    if self.owner is None:result['actual_lease_released']=True
                    else:result['actual_lease_released']=attempt('lease_release',lambda:self.owner.release_after_buffers(buffers_released=True))
        result['quarantine_required']=not (halted and result['hdmi_closed'] and result['buffers_released'] and result['actual_lease_released'])
        result['cleanup_complete']=bool(not result['quarantine_required'] and result['camera_released'] and not result['errors']
            and not any(v.get('error_bits') for v in joint['dma'].values()))
        self.cleanup=result
        return result

    def post_verify(self):
        if not self.cleanup or not self.cleanup['cleanup_complete']:raise RuntimeError('hardware cleanup must complete before reference')
        reference=VisionReference();rows=[]
        for raw,actual,stats in self.retained:
            expected=yuyv_to_bgr_q20(raw)
            pixel_mismatches=int(np.count_nonzero(actual[...,:3]!=expected))+int(np.count_nonzero(actual[...,3]))
            wanted=reference.process(expected,sequence=stats['source_sequence'],timestamp_ns=stats['timestamp_ns'])
            fields={k:{'reference':getattr(wanted,k),'pl':stats[k]} for k in STAT_FIELDS if getattr(wanted,k)!=stats[k]}
            rows.append({'source_sequence':stats['source_sequence'],'pixel_mismatch_bytes':pixel_mismatches,'stats_mismatches':fields})
        self.retained.clear()
        return {'matched':bool(rows) and all(not r['pixel_mismatch_bytes'] and not r['stats_mismatches'] for r in rows),
                'compared_frames':len(rows),'rows':rows,'scope':'first two camera frames only; not all-frame accuracy'}
