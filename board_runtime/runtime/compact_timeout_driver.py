"""Paired core-v20001 entry, retaining existing Native40/step1 timing policies."""
import time
if __package__:
    from .native40_boundary import Native40Main
    from .main_spatial_runtime import LiveBackend as OriginalLiveBackend
else:
    from native40_boundary import Native40Main
    from main_spatial_runtime import LiveBackend as OriginalLiveBackend


class TimeoutMain(Native40Main):
    def __init__(self,mmio,reader,*,clock=time.monotonic):
        # Exactly the original Sample40/NativeTransaction/Hardware initialization,
        # with the separately verified silicon version. No read-value masking.
        self.initialize_metrics();self.reader=reader
        self.mmio,self.clock=mmio,clock
        self.epoch=self.core_epoch=0;self.previous=None;self.next_sequence=0
        self.fault='';self.closed=False;self.deadline=None;self.active_deadline=None
        self.mode_b=None;self.counts=dict(sample=0);self._reply=None;self._controls=(32212255,True,False)
        if (mmio.read(0),mmio.read(4))!=(0x484d3235,0x20001):raise RuntimeError('timeout-safe silicon ID/version differs')
        if mmio.read(12)!=64 or mmio.read(24)!=0:raise RuntimeError('continuous hardware not a fresh isolated session')


class LiveBackend(OriginalLiveBackend):
    def snapshot(self):
        io=self.native.mmio
        if (io.read(0),io.read(4),io.read(24))!=(0x484d3235,0x20001,self.native.core_epoch):
            raise RuntimeError('timeout-safe final snapshot identity differs')
        accepted,completed=io.read(32),io.read(36);samples=self.native.counts['sample']
        if accepted!=completed or completed!=samples:raise RuntimeError('main final snapshot count differs')
        return dict(schema='v3b25_main_sample_snapshot_v1',accepted=accepted,completed=completed,
            driver_samples=samples,epoch=self.native.epoch,core_epoch=self.native.core_epoch,
            legacy_nlms_snapshot_issued=False,nlms_latency_cycles_measured=False)
