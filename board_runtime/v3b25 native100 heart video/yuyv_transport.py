"""One raw input copy; PL converts, fans out and writes the caller-owned frame."""
import time

import numpy as np

if __package__:
    from .joint_video_transport import _integer,UserStop,PAIR_GAP_NS
    from .yuyv_reference import validate_yuyv
else:
    from joint_video_transport import _integer,UserStop,PAIR_GAP_NS
    from yuyv_reference import validate_yuyv


INPUT_BYTES=614400
OUTPUT_BYTES=1228800


def _buffer_address(buffer,shape):
    if (not isinstance(buffer,np.ndarray) or buffer.dtype!=np.dtype('uint8')
        or buffer.shape!=shape or not buffer.flags.c_contiguous):
        raise ValueError('tightly packed uint8 CMA frame required')
    address=_integer(buffer.physical_address,'physical_address')
    if address<=0 or address%4 or address+buffer.nbytes>0x20000000:
        raise ValueError('frame outside reviewed aligned DDR aperture')
    return address


class YuyvPort:
    """A failed transfer retains its destination until owner-confirmed cleanup.

    take_completed_frame transfers ownership back to the caller, never to HDMI.
    The caller must then keep it until writeframe succeeds, or until all DMAs
    halt. display_owned must inspect the installed channel's owned frame list.
    """
    def __init__(self,core,reader,writer,gpio,color,input_buffer,*,is_loaded,cancelled,
                 display_owned,timeout=1.,clock=time.monotonic,sleep=time.sleep):
        if not 0<timeout<=5:raise ValueError('finite transfer timeout required')
        self.input_address=_buffer_address(input_buffer,(480,640,2))
        self.core,self.reader,self.writer,self.gpio,self.color=core,reader,writer,gpio,color
        self.input_buffer=input_buffer
        self.is_loaded,self.cancelled,self.display_owned=is_loaded,cancelled,display_owned
        self.timeout,self.clock,self.sleep=timeout,clock,sleep
        self.state='new';self.completed=0;self.epoch=None
        self.previous_sequence=self.previous_timestamp_ns=None
        self.active_destination=None

    def _available(self):
        if not self.is_loaded():raise RuntimeError('joint Overlay changed; refuse DMA access')
        if self.cancelled():raise UserStop('user stop requested')

    def start(self):
        if self.state!='new':raise RuntimeError('YUYV port already attempted')
        self._available()
        if self.core.read(0x0c)!=0 or self.gpio.read(8)!=0 or self.color.read(0)!=0 or self.gpio.read(0)&1:
            raise RuntimeError('YUYV/vision must start held in reset with empty mailbox')
        if self.reader.read(4)&0x770 or self.writer.read(0x34)&0x770:
            raise RuntimeError('DMA error at entry; status preserved')
        self.epoch=int(self.core.read(0x18))
        self.gpio.write(0,1)
        if not self.gpio.read(0)&1:raise RuntimeError('combined packet/color reset release not confirmed')
        self.state='ready'

    def _status(self):
        self._available()
        values=(int(self.reader.read(4)),int(self.writer.read(0x34)),int(self.core.read(0x0c)),
                int(self.gpio.read(8)),int(self.color.read(0)))
        if values[0]&0x770 or values[1]&0x770 or values[2]&8 or values[3]&1 or values[4]&1:
            raise RuntimeError('YUYV/vision/writeback fault; status preserved: '+repr(values))
        if int(self.core.read(0x18))!=self.epoch:raise RuntimeError('vision epoch changed')
        return values

    def _wait(self,predicate,deadline,label):
        while True:
            values=self._status()
            if predicate(*values):return values
            if self.clock()>=deadline:raise TimeoutError('YUYV '+label+' did not complete')
            self.sleep(.0002)

    def process(self,raw,destination,*,sequence,timestamp_ns):
        if self.state!='ready':raise RuntimeError('YUYV not ready; never retry an in-flight/failed frame')
        validate_yuyv(raw,camera_geometry=True)
        address=_buffer_address(destination,(480,640,4))
        coherent=bool(getattr(destination,'coherent',False))
        if not coherent and not all(callable(getattr(destination,n,None)) for n in ('flush','invalidate')):
            raise ValueError('noncoherent display frame requires explicit cache sync')
        if not (address+OUTPUT_BYTES<=self.input_address or self.input_address+INPUT_BYTES<=address):
            raise ValueError('input and output DMA frames overlap')
        if self.display_owned(address):raise RuntimeError('display still owns destination')
        sequence=_integer(sequence,'sequence');timestamp_ns=_integer(timestamp_ns,'timestamp_ns')
        if not 0<=sequence<=0xffffffff or timestamp_ns<0:raise ValueError('source token/time outside range')
        if self.previous_sequence is not None and (sequence<=self.previous_sequence or timestamp_ns<=self.previous_timestamp_ns):
            raise ValueError('source sequence/time must increase')
        self._available()
        elapsed=None if self.previous_timestamp_ns is None else timestamp_ns-self.previous_timestamp_ns
        missed=0 if self.previous_sequence is None else sequence-self.previous_sequence-1
        reason=('first_frame' if self.previous_sequence is None else 'sequence_gap' if missed
                else 'timestamp_gap' if elapsed>PAIR_GAP_NS else 'ok')
        self.state='transferring';self.active_destination=destination
        try:
            _,_,status,adapter,color=self._status()
            if status!=0 or adapter&0x1f or color&0x1f or adapter>>8!=(self.completed&0xffffff) or color>>8!=(self.completed&0xffffff):
                raise RuntimeError('mailbox/color/adapter not idle before source frame')
            np.copyto(self.input_buffer,raw,casting='no')
            self.input_buffer.flush()
            if not coherent:destination.flush()
            self.core.write(0x10,int(reason=='ok'));self.core.write(0x14,sequence);self.core.write(8,1)
            if not int(self.core.read(0x0c))&1:raise RuntimeError('vision ARM not confirmed')
            deadline=self.clock()+self.timeout
            self.writer.write(0x30,int(self.writer.read(0x30))|1)
            self._wait(lambda rd,wr,*rest:not wr&1,deadline,'S2MM start')
            self.writer.write(0x48,address);self.writer.write(0x4c,0);self.writer.write(0x58,OUTPUT_BYTES)
            self.reader.write(0,int(self.reader.read(0))|1)
            self._wait(lambda rd,*rest:not rd&1,deadline,'MM2S start')
            self.reader.write(0x18,self.input_address);self.reader.write(0x1c,0);self.reader.write(0x28,INPUT_BYTES)
            expected=(self.completed+1)&0xffffff
            def complete(rd,wr,core,adapter,color):
                if any(v>>8 not in (self.completed&0xffffff,expected) for v in (adapter,color)):
                    raise RuntimeError('unexpected color/adapter frame count')
                return bool(rd&2 and wr&2 and core&4 and not adapter&0x10 and not color&0x10
                            and adapter>>8==expected and color>>8==expected)
            self._wait(complete,deadline,'both DMAs and matched visual mailbox')
            if int(self.writer.read(0x58))!=OUTPUT_BYTES:raise RuntimeError('short S2MM writeback length')
            if not coherent:destination.invalidate()
            index,count,luma,diff,extrema,token,epoch=[int(self.core.read(o)) for o in range(0x20,0x3c,4)]
            valid=bool(extrema&(1<<24))
            if (index!=self.completed or count!=19200 or token!=sequence or epoch!=self.epoch
                or valid!=(reason=='ok') or extrema>>25 or not valid and (diff or (extrema>>16)&255)):
                raise RuntimeError('vision result identity/geometry/difference mismatch')
            if not int(self.core.read(0x0c))&4 or int(self.core.read(0x18))!=epoch:
                raise RuntimeError('visual mailbox replaced before ACK')
            result=dict(source_sequence=sequence,timestamp_ns=timestamp_ns,epoch=epoch,frame_index=index,
                source_previous_sequence=self.previous_sequence,pair_elapsed_ns=elapsed,missed_frames=missed,
                pixel_count=count,luma_sum=luma,luma_min=extrema&255,luma_max=(extrema>>8)&255,
                difference_valid=valid,reason=reason,diff_sum=diff if valid else None,
                diff_max=(extrema>>16)&255 if valid else None,writeback_bytes=OUTPUT_BYTES,
                destination_coherent=coherent,explicit_cache_sync=not coherent)
            self.core.write(8,2)
            if int(self.core.read(0x0c))!=0:raise RuntimeError('vision ACK did not clear mailbox')
            self.completed+=1
            self.previous_sequence,self.previous_timestamp_ns=sequence,timestamp_ns
            self.state='written'
            return result
        except BaseException:
            self.state='faulted'
            raise

    def take_completed_frame(self):
        if self.state!='written':raise RuntimeError('no completed frame available')
        self._available()
        result=self.active_destination
        self.active_destination=None;self.state='ready'
        return result
