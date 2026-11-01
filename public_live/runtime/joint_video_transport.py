"""One finite BGRX packet / immutable ROI mailbox. No hardware at import."""
from contextlib import contextmanager
from numbers import Integral
import time

import numpy as np

FRAME_BYTES=640*480*4
PAIR_GAP_NS=250_000_000


class UserStop(RuntimeError):
    pass


def _integer(value,name):
    if isinstance(value,(bool,np.bool_)) or not isinstance(value,Integral):
        raise TypeError(name+" must be an integer")
    return int(value)


def validate_frame(bgr):
    if not isinstance(bgr,np.ndarray) or bgr.dtype!=np.dtype("uint8"):
        raise TypeError("camera frame must be a uint8 NumPy BGR array")
    if bgr.shape!=(480,640,3):
        raise ValueError("camera frame must be 640x480 BGR")


class DeadlineMMIO:
    """Bound the installed VDMA driver's Python polling, without clearing errors.

    This does not make foreign C calls or a stalled physical AXI bus cancellable.
    The outer supervisor therefore never kills a potentially active DMA owner.
    """
    def __init__(self,mmio,*,is_loaded,clock=time.monotonic):
        self.mmio,self.is_loaded,self.clock=mmio,is_loaded,clock
        self.deadline=None
        self.label=""
        self.allow_halted_errors=False

    @contextmanager
    def budget(self,seconds,label,*,allow_halted_errors=False):
        if not 0<seconds<=5 or self.deadline is not None:
            raise ValueError("one positive bounded MMIO operation at a time")
        self.deadline,self.label=self.clock()+seconds,label
        self.allow_halted_errors=allow_halted_errors
        try:yield self
        finally:self.deadline=None;self.allow_halted_errors=False

    def _check(self):
        if self.deadline is None:
            raise RuntimeError("VDMA operation requires an explicit time budget")
        if self.clock()>=self.deadline:
            raise TimeoutError("VDMA "+self.label+" exceeded its MMIO budget")
        if not self.is_loaded():
            raise RuntimeError("joint Overlay changed; refuse VDMA access")

    def read(self,offset,*args,**kwargs):
        self._check()
        value=self.mmio.read(offset,*args,**kwargs)
        self._check()
        if offset==4 and int(value)&0xff0 and not (self.allow_halted_errors and int(value)&1):
            raise RuntimeError("HDMI VDMA error bits preserved: "+hex(int(value)))
        return value

    def write(self,offset,value):
        self._check()
        if offset==4 and int(value)&0xff0:
            raise ValueError("refuse to clear HDMI VDMA error bits")
        self.mmio.write(offset,value)
        self._check()


class VisionPort:
    """Sequential caller owns buffer until DMA + matching mailbox + ACK complete."""
    def __init__(self,core,dma,gpio,buffer,*,is_loaded,cancelled,
                 timeout=1.,clock=time.monotonic,sleep=time.sleep):
        if not 0<timeout<=5:
            raise ValueError("finite vision transfer timeout required")
        if buffer.shape!=(480,640,4) or buffer.dtype!=np.dtype("uint8") or buffer.nbytes!=FRAME_BYTES:
            raise ValueError("vision CMA buffer must be tightly packed BGRX32")
        address=_integer(buffer.physical_address,"physical_address")
        if address<=0 or address%4 or address+FRAME_BYTES>0x20000000:
            raise ValueError("vision buffer outside reviewed 512MiB DDR window/alignment")
        self.core,self.dma,self.gpio,self.buffer=core,dma,gpio,buffer
        self.is_loaded,self.cancelled=is_loaded,cancelled
        self.timeout,self.clock,self.sleep=timeout,clock,sleep
        self.address=address
        self.state="new"
        self.epoch=None
        self.completed=0
        self.previous_sequence=self.previous_timestamp_ns=None

    def _available(self):
        if not self.is_loaded():
            raise RuntimeError("joint Overlay changed; refuse vision access")
        if self.cancelled():
            raise UserStop("user stop requested")

    def start(self):
        if self.state!="new":
            raise RuntimeError("vision port already attempted")
        self._available()
        if self.core.read(0x0c)!=0 or self.gpio.read(8)!=0 or self.gpio.read(0)&1:
            raise RuntimeError("vision must start from owner-confirmed reset/empty mailbox")
        if self.dma.read(4)&0x770:
            raise RuntimeError("vision DMA already has error bits")
        self.epoch=int(self.core.read(0x18))
        self.gpio.write(0,1)
        if not self.gpio.read(0)&1:
            raise RuntimeError("vision packet reset release not confirmed")
        self.state="ready"

    def _status(self):
        self._available()
        dma=int(self.dma.read(4))
        core=int(self.core.read(0x0c))
        adapter=int(self.gpio.read(8))
        if dma&0x770 or core&8 or adapter&1:
            raise RuntimeError("vision transport fault (status preserved): "+
                               repr(dict(dma=hex(dma),core=hex(core),adapter=hex(adapter))))
        if int(self.core.read(0x18))!=self.epoch:
            raise RuntimeError("vision epoch changed during transfer")
        return dma,core,adapter

    def _wait(self,predicate,deadline,label):
        while True:
            values=self._status()
            if predicate(*values):return values
            if self.clock()>=deadline:
                raise TimeoutError("vision "+label+" did not complete")
            self.sleep(.0002)

    def process(self,bgr,*,sequence,timestamp_ns):
        if self.state!="ready":
            raise RuntimeError("vision not ready; never retry a failed/in-flight frame")
        validate_frame(bgr)
        sequence=_integer(sequence,"sequence")
        timestamp_ns=_integer(timestamp_ns,"timestamp_ns")
        if not 0<=sequence<=0xffffffff or timestamp_ns<0:
            raise ValueError("source token/time outside supported range")
        if self.previous_sequence is not None and (sequence<=self.previous_sequence or timestamp_ns<=self.previous_timestamp_ns):
            raise ValueError("source sequence and read-completion timestamp must increase")
        self._available()
        elapsed=None if self.previous_timestamp_ns is None else timestamp_ns-self.previous_timestamp_ns
        missed=0 if self.previous_sequence is None else sequence-self.previous_sequence-1
        reason=("first_frame" if self.previous_sequence is None else "sequence_gap" if missed
                else "timestamp_gap" if elapsed>PAIR_GAP_NS else "ok")
        compare=reason=="ok"
        self.state="transferring"
        try:
            _,status,adapter=self._status()
            if status!=0 or adapter&0x1f or adapter>>8!=(self.completed&0xffffff):
                raise RuntimeError("mailbox/adapter not idle at new source frame")
            self.buffer[...,:3]=bgr
            self.buffer[...,3]=0
            self.buffer.flush()
            self.core.write(0x10,int(compare))
            self.core.write(0x14,sequence)
            self.core.write(8,1)
            if not int(self.core.read(0x0c))&1:
                raise RuntimeError("vision ARM not confirmed")
            deadline=self.clock()+self.timeout
            self.dma.write(0,int(self.dma.read(0))|1)
            self._wait(lambda dma,core,adapter:not dma&1,deadline,"MM2S start")
            self.dma.write(0x18,self.address)
            self.dma.write(0x28,FRAME_BYTES)
            expected_count=(self.completed+1)&0xffffff
            def complete(dma,core,adapter):
                if adapter>>8 not in (self.completed&0xffffff,expected_count):
                    raise RuntimeError("vision adapter delivered unexpected frame count")
                return bool(dma&2 and core&4 and not adapter&0x10 and adapter>>8==expected_count)
            self._wait(complete,deadline,"DMA/mailbox/adapter")
            words=[int(self.core.read(offset)) for offset in range(0x20,0x3c,4)]
            index,count,luma,diff,extrema,token,epoch=words
            valid=bool(extrema&(1<<24))
            if (index!=self.completed or count!=19200 or token!=sequence or epoch!=self.epoch
                    or valid!=compare or extrema>>25 or not valid and (diff or (extrema>>16)&255)):
                raise RuntimeError("vision result identity/geometry/difference validity mismatch")
            if not int(self.core.read(0x0c))&4 or int(self.core.read(0x18))!=epoch:
                raise RuntimeError("vision result was replaced before ACK")
            result=dict(source_sequence=sequence,timestamp_ns=timestamp_ns,epoch=epoch,frame_index=index,
                source_previous_sequence=self.previous_sequence,pair_elapsed_ns=elapsed,missed_frames=missed,
                pixel_count=count,luma_sum=luma,luma_min=extrema&255,luma_max=(extrema>>8)&255,
                difference_valid=valid,reason=reason,diff_sum=diff if valid else None,
                diff_max=(extrema>>16)&255 if valid else None)
            self.core.write(8,2)
            if int(self.core.read(0x0c))!=0:
                raise RuntimeError("vision ACK did not clear pending mailbox")
            self.completed+=1
            self.previous_sequence,self.previous_timestamp_ns=sequence,timestamp_ns
            self.state="ready"
            return result
        except BaseException:
            self.state="faulted"
            raise
