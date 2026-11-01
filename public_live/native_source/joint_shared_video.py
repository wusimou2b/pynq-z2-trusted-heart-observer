"""Attach video to the real heart owner; never construct/open a second owner."""
from types import SimpleNamespace

import numpy as np

if __package__:
    from .joint_video_pack import NativeResources,NativePort,METHOD
    from .joint_video_transport import VisionPort,DeadlineMMIO,validate_frame
else:
    from joint_video_pack import NativeResources,NativePort,METHOD
    from joint_video_transport import VisionPort,DeadlineMMIO,validate_frame


class _JointLabels:
    def __init__(self,cv):self.cv=cv
    def __getattr__(self,name):return getattr(self.cv,name)
    def putText(self,image,text,*args,**kwargs):
        prefix='LIVE PL | HEART OFF | seq='
        if text.startswith(prefix):text='JOINT 5fps | HEART: NOTEBOOK | seq='+text[len(prefix):]
        elif 'HEART OFF' in text:raise RuntimeError('frozen video label contract changed')
        return self.cv.putText(image,text,*args,**kwargs)


class _ReadyFrame:
    def __init__(self,bgr):self.bgr=bgr
    def read(self):
        if self.bgr is None:raise RuntimeError('selected camera frame already consumed')
        bgr,self.bgr=self.bgr,None
        return True,bgr


class SharedVideoResources(NativeResources):
    def __init__(self,*args,owner,identity,api,lease,preflight,**kwargs):
        super().__init__(*args,**kwargs)
        self.owner,self.lease=owner,lease
        self.api=SimpleNamespace(**vars(api));self.api.cv2=_JointLabels(api.cv2)
        self.joint_identity,self.preflight=identity,preflight

    def open(self):
        if self.stage!='new':raise RuntimeError('shared video resources already attempted')
        if self.owner.state!='bound' or not self.owner._hardware.is_loaded():
            raise RuntimeError('shared video requires the current bound heart owner')
        self._stage('shared_camera_startup');cv=self.api.cv2
        self.camera=cv.VideoCapture('/dev/video0',cv.CAP_V4L2)
        if not self.camera.isOpened():raise RuntimeError('camera /dev/video0 could not open; no retry')
        if not callable(getattr(self.camera,'grab',None)) or not callable(getattr(self.camera,'retrieve',None)):
            raise RuntimeError('camera grab/retrieve capability required; no buffered read fallback')
        self.camera.set(cv.CAP_PROP_FRAME_WIDTH,640);self.camera.set(cv.CAP_PROP_FRAME_HEIGHT,480)
        self.camera.set(cv.CAP_PROP_FOURCC,cv.VideoWriter_fourcc(*'YUYV'))
        ok,first=self.camera.read()
        if not ok:raise RuntimeError('camera startup read failed')
        validate_frame(first);del first
        fourcc=int(self.camera.get(cv.CAP_PROP_FOURCC))
        camera=dict(device='/dev/video0',opencv_version=cv.__version__,image_size=[640,480],
            fourcc=''.join(chr((fourcc>>(8*i))&255) for i in range(4)),
            driver_reported_fps_not_measured=self.camera.get(cv.CAP_PROP_FPS),startup_read_not_in_formal_counts=True)
        if camera['fourcc']!='YUYV':raise RuntimeError('camera did not accept reviewed YUYV')
        self._available();self._stage('shared_explicit_hdmi_binding')
        view=self.owner._hardware._overlay;self.vdma=view.hdmi_vdma
        if self.vdma.framecount!=4 or hasattr(self.vdma,'readchannel'):
            raise RuntimeError('HDMI VDMA must have four MM2S-only frame stores')
        channel=self.vdma.writechannel
        self.guard=DeadlineMMIO(channel._mmio,is_loaded=self.owner._hardware.is_loaded)
        channel._mmio=self.guard
        if hasattr(channel._frames,'_mmio'):channel._frames._mmio=self.guard
        self.hdmi=self.api.VideoOut(view.hierarchy_dict['hdmi_out'],vdma=self.vdma)
        self._stage('shared_hdmi_configure')
        with self.guard.budget(5,'configure'):self.hdmi.configure(self.api.VideoMode(640,480,24,60))
        self._available();self._stage('shared_hdmi_start')
        with self.guard.budget(3,'start'):self.hdmi.start()
        raw=self.owner._io['hdmi_vdma']
        if raw.read(0)&2 or raw.read(0x54)!=1920 or raw.read(0x58)&0xffffff!=1920 or raw.read(0x50)!=480:
            raise RuntimeError('HDMI geometry/parking readback mismatch')
        self._available();self._stage('shared_vision_allocate')
        self.buffer=self.api.allocate(shape=(480,640,4),dtype=np.uint8,cacheable=True)
        port=VisionPort(self.owner._io['vision_0'],self.owner._io['vision_dma'],self.owner._io['vision_control'],
            self.buffer,is_loaded=self.owner._hardware.is_loaded,cancelled=self.cancelled)
        self.port=NativePort(port,mix_channels=cv.mixChannels,clock_ns=self.clock_ns);port.start()
        self._stage('shared_video_ready')
        return dict(joint_identity=self.joint_identity,camera=camera,driver_identity=self.api.driver_identity,
            hdmi_mode=dict(width=640,height=480,bits_per_pixel=24,configured_refresh_hz_not_camera_fps=60),
            shared_existing_owner=True,packing_method=METHOD,packing_preflight=self.preflight,
            reference_mode='two_frames_checked_only_after_hardware_cleanup',verification_ram_limit_bytes=1843200,
            image_history_saved=False,buffer_policy='one shared-owner BGRX buffer; original four-slot HDMI cache')

    def process_ready_frame(self,bgr,*,sequence,timestamp_ns):
        validate_frame(bgr);camera=self.camera
        try:
            self.camera=_ReadyFrame(bgr)
            return self.process_frame(sequence=sequence,timestamp_ns=timestamp_ns)
        finally:self.camera=camera
