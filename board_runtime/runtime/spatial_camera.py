"""Camera-only spatial features; original video timing and resource close retained."""
import json
from pathlib import Path
import time

import numpy as np

if __package__:
    from .yuyv_runtime import Resources
    from .joint_video_runtime import describe
    from .joint_video_transport import DeadlineMMIO
    from .joint_video_five import VideoFive
    from .yuyv_reference import validate_yuyv,yuyv_to_bgr_q20
    from .spatial_owner import SpatialOwner
    from .spatial_transport import SpatialPort
    from .spatial_features import Features,summarize
    from ..vision_reference import gray_downsample_bgr
    from ..spatial_reference import spatial_stats
else:
    from yuyv_runtime import Resources
    from joint_video_runtime import describe
    from joint_video_transport import DeadlineMMIO
    from joint_video_five import VideoFive
    from yuyv_reference import validate_yuyv,yuyv_to_bgr_q20
    from spatial_owner import SpatialOwner
    from spatial_transport import SpatialPort
    from spatial_features import Features,summarize
    from vision_reference import gray_downsample_bgr
    from spatial_reference import spatial_stats


def write_state(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    temporary.replace(path)


class CameraResources(Resources):
    def __init__(self,*args,clock_ns=time.monotonic_ns,**kwargs):
        kwargs.setdefault('owner_factory',SpatialOwner)
        super().__init__(*args,**kwargs)
        self.motion_clock=clock_ns;self.feature_source=Features();self.formal_epoch=None;self.last_phase=None

    def open(self):
        # Frozen Resources.open ordering; only the new owner/port identity and T8 differ.
        if self.stage!='new':raise RuntimeError('resources already attempted')
        self._stage('imports');self.api=self.api_factory()
        self.owner=self.owner_factory(self.directory,on_event=self.on_event)
        self._stage('explicit_spatial_overlay');identity=self.owner.open()
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
        self.port=SpatialPort(self.owner._io['vision_0'],self.owner._io['vision_dma'],self.owner._io['display_dma'],
            self.owner._io['vision_control'],self.owner._io['yuyv_control'],self.input,
            is_loaded=self.owner._hardware.is_loaded,cancelled=self.cancelled,display_owned=display_owned)
        self.port.start();self.port.set_threshold(8);self._stage('ready')
        return dict(joint_identity=identity,raw_camera_format='YUYV',hdmi_format='BGRX32',hdmi_stride=2560,
            hdmi_cacheable_requested=False,driver_identity=self.api.driver_identity,
            cache_policy='noncoherent frames flush before S2MM, invalidate after; never override coherent flag',
            same_input_reference_scope='first two frames after confirmed hardware cleanup',retained_ram_limit_bytes=3686400,
            heart_capture_started=False,pixel_threshold=8,grid=[4,3])

    def arm(self,epoch):
        if self.formal_epoch is not None:raise RuntimeError('spatial feature collection already armed')
        self.formal_epoch=epoch

    def process_ready_frame(self,raw,*,sequence,timestamp_ns):
        if self.formal_epoch is None:raise RuntimeError('spatial feature collection not armed')
        self._available();validate_yuyv(raw,camera_geometry=True);self.captured+=1
        self._stage('new_display_frame');self.pending=self.hdmi.newframe()
        self._stage('pl_color_roi_writeback')
        result=self.port.process(raw,self.pending,sequence=sequence,timestamp_ns=timestamp_ns)
        if self.port.take_completed_frame() is not self.pending:raise RuntimeError('destination ownership changed')
        if len(self.retained)<2:self.retained.append((raw.copy(),np.array(self.pending,copy=True),dict(result)))
        self._stage('hdmi_submit')
        with self.guard.budget(1,'frame submit'):
            while not int(self.guard.read(4))&0x1000:
                self._available();time.sleep(.001)
            self._available();checked_ns=self.motion_clock()
            features=self.feature_source.consume(result,elapsed_ns=timestamp_ns-self.formal_epoch,now_ns=checked_ns)
            cv=self.api.cv2
            cv.rectangle(self.pending,(160,120),(479,359),(0,255,0,0),1)
            for x in (240,320,400):cv.line(self.pending,(x,120),(x,359),(0,120,0,0),1)
            for y in (200,280):cv.line(self.pending,(160,y),(479,y),(0,120,0,0),1)
            cv.putText(self.pending,'DO: '+features['phase_label']+' | '+str(features['phase_remaining_seconds'])+'s left',
                (10,22),cv.FONT_HERSHEY_SIMPLEX,.55,(0,255,255,0),1)
            ratio='N/A' if features['motion_pixel_ratio'] is None else '%.3f'%features['motion_pixel_ratio']
            maximum='N/A' if features['max_block_mean_difference'] is None else '%.2f'%features['max_block_mean_difference']
            cv.putText(self.pending,'FEATURES ONLY | HEART OFF | seq='+str(sequence),
                (10,44),cv.FONT_HERSHEY_SIMPLEX,.45,(0,255,255,0),1)
            cv.putText(self.pending,'T=8 | changed='+ratio+' | max-block-mean='+maximum,
                (10,65),cv.FONT_HERSHEY_SIMPLEX,.43,(0,255,255,0),1)
            self.hdmi.writeframe(self.pending)
        self.pending=None;self.submitted+=1;self._stage('ready')
        if features['phase_index']!=self.last_phase:
            self.last_phase=features['phase_index']
            print('DO: '+features['phase_label']+'；仅动作要求，本次不分类。',flush=True)
        return dict(source_sequence=sequence,read_completed_ns=timestamp_ns,vision=result,features=features,hdmi_submitted=True)

    def post_verify(self):
        if not self.cleanup or not self.cleanup['cleanup_complete']:raise RuntimeError('hardware cleanup must complete before reference')
        samples=list(self.retained)
        try:
            report=super().post_verify();previous=None;rows=[]
            for raw,actual,stats in samples:
                current=gray_downsample_bgr(yuyv_to_bgr_q20(raw))[60:180,80:240]
                wanted=spatial_stats(current,previous,threshold=8,compare_enable=stats['difference_valid'])
                mismatch={k:dict(reference=v,pl=stats['spatial'].get(k)) for k,v in wanted.items() if stats['spatial'].get(k)!=v}
                rows.append(dict(source_sequence=stats['source_sequence'],mismatches=mismatch));previous=current.copy()
            report.update(spatial_compared_frames=len(rows),spatial_rows=rows)
            report['matched']=report['matched'] and bool(rows) and not any(r['mismatches'] for r in rows)
            return report
        finally:self.retained.clear();samples.clear()


def run_session(root,output,*,resource_factory=CameraResources,clock_ns=time.monotonic_ns):
    root,output=Path(root),Path(output);output.mkdir(exist_ok=False)
    report=dict(schema='v3b25_spatial_camera_run_v1',fault=None,cleanup={},classification_performed=False,thresholds_refitted=False,
        heart_capture_started=False,imu_capture_started=False,heart_ps_started=False,requested_formal_seconds=60,target_fps=5,
        startup_timeout_seconds=180,pixel_threshold=8,grid=[4,3],images_saved=False,formal_reference_calls=0,
        all_frames_reference_verified=False,three_class_acceptance_passed=False,accuracy_verified=False,
        full_v3b_acceptance_passed=False,board_ddr_verified=False,screen_dynamic_observed=None,human_protocol_confirmed=None)
    resource=video=None;began=clock_ns();formal=None;stopped=lambda:(root/'stop.request').exists()
    def event(value):
        if formal is None:
            if stopped():raise RuntimeError('startup stop requested')
            if clock_ns()-began>180_000_000_000:raise TimeoutError('original180s startup budget exceeded')
            write_state(root/'startup-progress.json',value)
    try:
        event(dict(stage='imports',monotonic_ns=clock_ns()))
        resource=resource_factory(root,cancelled=stopped,on_event=event,clock_ns=clock_ns)
        report['identity']=resource.open()
        if stopped():raise RuntimeError('stop requested before formal window')
        video=VideoFive(resource,output,clock_ns=clock_ns)
        formal=clock_ns();resource.arm(formal);video.arm(formal);report['startup_seconds']=(formal-began)/1e9
        write_state(root/'formal-ready.json',dict(formal_started_ns=formal))
        print('READY：60秒空间特征采集；静止→轻动→强动→静止各15秒。FEATURES ONLY / HEART OFF。',flush=True)
        video.start()
        while video.is_alive():
            if stopped():video.request_stop()
            video.join(.2)
    except BaseException as exc:report['fault']=describe(exc,getattr(resource,'stage','imports'))
    finally:
        if video is not None:
            video.request_stop()
            if not video.join(10):
                report['cleanup']=dict(cleanup_complete=False,quarantine_required=True,reason='video thread still active; hardware close/free not attempted')
            report['video']=video.report()
        if not report['cleanup'] and resource is not None:
            try:report['cleanup']=resource.close()
            except BaseException as exc:report['cleanup']=dict(cleanup_complete=False,quarantine_required=True,error=describe(exc,'close'))
        elif resource is None:report['cleanup']=dict(cleanup_complete=True,quarantine_required=False,hardware_open_not_attempted=True)
    if report['cleanup'].get('cleanup_complete') and resource is not None:
        try:report['post_verification']=resource.post_verify()
        except BaseException as exc:report['post_verification']=dict(matched=False,error=describe(exc,'reference'))
    vr=report.get('video',{});n=vr.get('metrics',{}).get('records_saved',0)
    report['counts']=dict(records_saved=n,captured=getattr(resource,'captured',0),submitted=getattr(resource,'submitted',0),
        pl_completed=getattr(getattr(resource,'port',None),'completed',0))
    report['session_complete']=bool(report['fault'] is None and vr.get('fault') is None and vr.get('stop_reason')=='duration_complete'
        and vr.get('thread_exited') and vr.get('metrics',{}).get('formal_elapsed_seconds',0)>=60 and n>=3
        and all(v==n for v in report['counts'].values()) and report['cleanup'].get('cleanup_complete')
        and report.get('post_verification',{}).get('matched') and report.get('post_verification',{}).get('compared_frames')==2
        and report.get('post_verification',{}).get('spatial_compared_frames')==2)
    if report['session_complete']:
        try:
            with (output/'frames.jsonl').open(encoding='utf-8') as stream:rows=[json.loads(line) for line in stream]
            if len(rows)!=n:raise ValueError('feature journal count differs')
            report['feature_summary']=summarize(rows,formal)
            with (output/'feature-summary.json').open('x',encoding='utf-8') as sink:
                json.dump(report['feature_summary'],sink,ensure_ascii=False,indent=2,allow_nan=False)
        except BaseException as exc:report['session_complete']=False;report['summary_error']=describe(exc,'summary')
    retained=(resource,video) if report['cleanup'].get('quarantine_required') else None
    return report,retained
