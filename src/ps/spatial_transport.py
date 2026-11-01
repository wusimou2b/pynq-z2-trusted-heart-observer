"""Capture the v2 spatial bank before the original YUYV transport ACK."""
from types import SimpleNamespace

if __package__:
    from .yuyv_transport import YuyvPort
    from .spatial_mailbox import read_spatial_result
else:
    from yuyv_transport import YuyvPort
    from spatial_mailbox import read_spatial_result


class _Capture:
    def __init__(self,raw):self.raw=raw;self.last=None;self.seen={};self.expected=None;self.check=lambda:None
    def bank_read(self,offset):
        self.check();value=self.raw.read(offset);self.check();return value
    def read(self,offset):
        value=self.raw.read(offset)
        if offset in range(0x20,0x3c,4):self.seen[offset]=value
        return value
    def write(self,offset,value):
        if (offset,value)==(8,1):self.last=None;self.seen={}
        if (offset,value)==(8,2):
            snap=read_spatial_result(SimpleNamespace(read=self.bank_read))
            flags=(int(snap['difference_valid'])<<24)|((snap['diff_max'] or 0)<<16)|(snap['luma_max']<<8)|snap['luma_min']
            actual=[snap['frame_index'],snap['pixel_count'],snap['luma_sum'],snap['diff_sum'] or 0,flags,snap['source_sequence'],snap['epoch']]
            if [self.seen.get(o) for o in range(0x20,0x3c,4)]!=actual or (snap['frame_index'],snap['source_sequence'],snap['epoch'])!=self.expected:
                raise RuntimeError('spatial bank differs from same-transfer legacy snapshot')
            self.last=snap
            self.check()
        self.raw.write(offset,value)


class SpatialPort(YuyvPort):
    def __init__(self,core,*args,**kwargs):
        self.capture=_Capture(core)
        super().__init__(self.capture,*args,**kwargs)
        self.spatial_deadline=None;self.capture.check=self._check_bank

    def _check_bank(self):
        self._available()
        if self.spatial_deadline is None or self.clock()>=self.spatial_deadline:
            raise TimeoutError('spatial bank read/ACK exceeded original transfer budget')

    def start(self):
        if (int(self.core.read(0)),int(self.core.read(4)))!=(0x56334232,0x20000):raise RuntimeError('spatial v2 silicon required')
        super().start()

    def set_threshold(self,value):
        if type(value) is not int or not 1<=value<=255:raise ValueError('pixel threshold must be integer1..255')
        if self.state!='ready':raise RuntimeError('threshold only before an idle transfer')
        self._available()
        if self.core.read(12)!=0:raise RuntimeError('threshold requires idle mailbox')
        self.core.write(0x1c,value)
        if self.core.read(0x1c)!=value:self.state='faulted';raise RuntimeError('pixel threshold configuration not confirmed')

    def process(self,raw,destination,*,sequence,timestamp_ns):
        self.capture.expected=(self.completed,sequence,self.epoch)
        self.spatial_deadline=self.clock()+self.timeout
        result=super().process(raw,destination,sequence=sequence,timestamp_ns=timestamp_ns)
        if self.capture.last is None:
            self.state='faulted';raise RuntimeError('missing spatial snapshot')
        return dict(result,spatial=self.capture.last)
