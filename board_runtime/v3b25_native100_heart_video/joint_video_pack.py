"""Direct native BGR copy into the original buffer; protocol/zero/flush unchanged."""
import hashlib
import time

import numpy as np

if __package__:
    from .joint_video_live import LiveResources,MeasuredPort
    from .joint_video_transport import validate_frame
else:
    from joint_video_live import LiveResources,MeasuredPort
    from joint_video_transport import validate_frame

METHOD='opencv_mix_channels_direct_bgr_to_existing_bgrx_preserve_zero_x_v1'


def pack_bgr(source,target,mix_channels):
    validate_frame(source)
    if not isinstance(target,np.ndarray) or target.dtype!=np.dtype('uint8'):
        raise TypeError('native destination must be a uint8 NumPy buffer')
    if target.shape!=(480,640,4) or not target.flags.c_contiguous:
        raise ValueError('native destination must be tightly packed 640x480 BGRX')
    result=mix_channels([source],[target],(0,0,1,1,2,2))
    if (not isinstance(result,(tuple,list)) or len(result)!=1 or not isinstance(result[0],np.ndarray)
            or result[0].shape!=target.shape or result[0].dtype!=target.dtype
            or result[0].strides!=target.strides
            or result[0].__array_interface__['data'][0]!=target.__array_interface__['data'][0]):
        raise RuntimeError('native converter replaced the destination; no fallback')


def packing_preflight(cv):
    """Actual installed cv2, ordinary RAM only, before opening the hardware owner."""
    began=time.monotonic_ns();rows=[]
    source=(np.arange(480*640*3,dtype=np.uint32).reshape(480,640,3)*37+11).astype(np.uint8)
    for name in ('pattern','reverse','extremes'):
        if name=='extremes':source[:]=[0,255,127]
        current=source[:,::-1,:] if name=='reverse' else source
        expected=np.full((480,640,4),173,np.uint8);actual=np.full_like(expected,173)
        expected[...,:3]=current;expected[...,3]=0
        pack_bgr(current,actual,cv.mixChannels)
        if not np.all(actual[...,3]==173):raise RuntimeError('native packing modified X before original zero step')
        actual[...,3]=0
        matched=np.array_equal(expected,actual)
        if not matched:raise RuntimeError('native packing bytes differ from original NumPy packing')
        rows.append(dict(name=name,matched=True,direct_destination=True,x_zero=True,byte_count=actual.nbytes,
            actual_sha256=hashlib.sha256(actual.tobytes()).hexdigest(),
            expected_sha256=hashlib.sha256(expected.tobytes()).hexdigest()))
    return dict(passed=True,method=METHOD,opencv_version=cv.__version__,numpy_version=np.__version__,
        before_hardware_open=True,ordinary_ram_only=True,images_saved=False,cases=rows,
        elapsed_ms=(time.monotonic_ns()-began)/1e6)


class _NativeBuffer:
    def __init__(self,raw,mix_channels):self.raw,self.mix_channels=raw,mix_channels
    def __setitem__(self,index,value):
        if index==(Ellipsis,slice(None,3)):pack_bgr(value,self.raw,self.mix_channels)
        elif index==(Ellipsis,3):self.raw[index]=value
        else:raise RuntimeError('original finite buffer assignment contract changed')
    def flush(self):return self.raw.flush()


class NativePort(MeasuredPort):
    """Only the original first buffer assignment changes; finally restores raw CMA."""
    def __init__(self,port,*,mix_channels,clock_ns=time.monotonic_ns):
        super().__init__(port,clock_ns=clock_ns);self.mix_channels=mix_channels

    def process(self,*args,**kwargs):
        if self.busy:raise RuntimeError('one finite video transfer at a time')
        raw=self.port.buffer
        try:
            self.port.buffer=_NativeBuffer(raw,self.mix_channels)
            return super().process(*args,**kwargs)
        finally:self.port.buffer=raw


class NativeResources(LiveResources):
    def process_frame(self,**kwargs):
        result=super().process_frame(**kwargs)
        result['packing_method']=METHOD
        self.last_frame['packing_method']=METHOD
        return result

    def open(self):
        factory=self.api_factory;preflight=None
        def checked_factory():
            nonlocal preflight
            api=factory()
            preflight=packing_preflight(api.cv2)
            return api
        self.api_factory=checked_factory
        try:identity=super().open()
        finally:self.api_factory=factory
        self.port=NativePort(self.port.port,mix_channels=self.api.cv2.mixChannels,clock_ns=self.clock_ns)
        identity.update(packing_method=METHOD,packing_preflight=preflight)
        return identity
