"""Owner-only unified main-chain driver. No arithmetic fallback or PYNQ import.

One20ms deadline covers writes, poll, bounded return AND ACK. The outer
original one-second step/freshness policy remains independently enforced.
"""
from dataclasses import dataclass
import hashlib
import math
import struct
import time

if __package__:
    from .small_heart_model import Identity,BranchResult,BRANCHES,_identity
else:
    from small_heart_model import Identity,BranchResult,BRANCHES,_identity

COMMAND_SECONDS=.020
REASONS=('history_short','contact_blocked','model_clipped','actual_amplitude_power_protection',
         'actual_gain_protection','degenerate_reference_or_ppg','no_active_axes','nonfinite_candidate',
         'poor_rms','poor_power','insufficient_magnitude_benefit','candidate_axis_worsening','benefit_confirmed','cooldown')


@dataclass(frozen=True)
class SampleRequest:
    identity: Identity
    valid: bool
    reset: bool
    ir_raw: float | None
    references: tuple
    contact_ready: bool
    contact_allowed: bool=True
    beta_int: int=32212255


@dataclass(frozen=True)
class SampleResult:
    identity: Identity
    core_epoch: int
    raw: float | None
    mean: float | None
    reply: object
    joint: float | None
    mix: float
    reason: str
    protection: bool
    checked: bool
    branches: dict
    transaction_seconds: float


def word(value):return struct.unpack('<Q',struct.pack('<d',float(value)))[0]
def floating(value):return struct.unpack('<d',struct.pack('<Q',value))[0]


class HardwareMainChain:
    source='pl_mmio'

    def __init__(self,mmio,*,clock=time.monotonic):
        self.mmio,self.clock=mmio,clock
        self.epoch=self.core_epoch=0;self.previous=None;self.next_sequence=0
        self.fault='';self.closed=False;self.deadline=None;self.active_deadline=None
        self.mode_b=None
        self.counts=dict(sample=0);self._reply=None;self._controls=(32212255,True,False)
        if (mmio.read(0),mmio.read(4))!=(0x484d3235,0x20000):
            raise RuntimeError('continuous main-chain silicon ID/version differs')
        if mmio.read(12)!=64 or mmio.read(24)!=0:
            raise RuntimeError('continuous hardware not a fresh isolated session')

    def set_deadline(self,deadline):
        if not isinstance(deadline,(int,float)) or not math.isfinite(deadline):
            raise ValueError('absolute original step deadline required')
        self.deadline=deadline

    def _begin(self):
        self.started=self.clock();self.active_deadline=self.started+COMMAND_SECONDS
        if self.deadline is not None:self.active_deadline=min(self.active_deadline,self.deadline)
        self._time()

    def _time(self):
        now=self.clock()
        if self.active_deadline is not None and now>=self.active_deadline:
            raise TimeoutError('continuous whole20ms transaction/step deadline expired; no retry')
        return now

    def _read(self,address):
        self._time();value=self.mmio.read(address);self._time()
        if type(value) is not int or not 0<=value<=0xffffffff:
            raise RuntimeError('continuous MMIO word invalid')
        return value

    def _write(self,address,value):
        self._time();self.mmio.write(address,value);self._time()

    def _read64(self,index):
        lo=self._read(0x1000+8*index);hi=self._read(0x1004+8*index)
        return lo | hi<<32

    def _float(self,index):
        value=floating(self._read64(index))
        if not math.isfinite(value):raise RuntimeError('nonfinite continuous result')
        return value

    def _poll(self):
        while True:
            status=self._read(12)
            if status&12:raise RuntimeError(f'continuous hardware locked/stopped status={status:08x} code={self._read(40):02x}')
            if not status&1:
                if not status&2 or not status&64:raise RuntimeError('continuous result not ready/quiescent')
                return status

    def _ack(self):
        self._write(8,4)
        if self._read(12)&7:raise RuntimeError('continuous ACK did not consume result')
        self._time()

    def reset(self):
        return self._initialize(True)

    def initialize_legacy(self):
        return self._initialize(False)

    def _initialize(self,mode_b):
        if self.epoch or self.closed or self.fault:raise RuntimeError('continuous initializes once; no retry')
        try:
            command=3 if mode_b else 1
            self._begin();self._write(8,command);status=self._poll()
            if status&48!=(48 if mode_b else 16) or self._read(28)!=command or self._read(24)!=1:
                raise RuntimeError('continuous initialization identity/mode differs')
            self.epoch=self.core_epoch=1;self.mode_b=mode_b;self._ack()
            return self.epoch
        except BaseException as exc:
            self.fault=str(exc) or type(exc).__name__;raise

    def _validate(self,request):
        if not isinstance(request,SampleRequest):raise ValueError('continuous sample type differs')
        _identity(request.identity);ident=request.identity
        if any(v>0xffffffffffffffff for v in (ident.request_id,ident.sequence,ident.generation)):
            raise ValueError('continuous identity exceeds64 bits')
        if (any(type(getattr(request,k)) is not bool for k in ('valid','reset','contact_ready','contact_allowed'))
            or type(request.beta_int) is not int or request.beta_int!=32212255
            or not isinstance(request.references,tuple) or len(request.references)!=4
            or not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in request.references)):
            raise ValueError('continuous sample controls/references invalid')
        reset=(not request.valid or self.previous is None or ident.generation!=self.previous[0].generation
               or request.valid!=self.previous[1])
        if (request.reset!=reset or ident.sequence!=self.next_sequence or
            self.previous is not None and (ident.run_id!=self.previous[0].run_id or ident.request_id<=self.previous[0].request_id)):
            raise ValueError('continuous sample reset/identity/order differs')
        if not request.valid:
            if request.ir_raw is not None or request.references!=(0.,0.,0.,0.) or request.contact_ready:
                raise ValueError('invalid continuous slot requires zero packet')
        elif isinstance(request.ir_raw,bool) or not isinstance(request.ir_raw,(int,float)) or not math.isfinite(request.ir_raw):
            raise ValueError('continuous IR must be finite')

    def _encode(self,request):
        ident=request.identity
        run=int.from_bytes(hashlib.sha256(ident.run_id.encode('utf-8')).digest()[:16],'little')
        values=[run>>(i*32)&0xffffffff for i in range(4)]
        for v in (ident.request_id,ident.sequence,ident.generation):values.extend((v&0xffffffff,v>>32))
        flags=int(request.valid)|int(request.reset)<<1|int(request.contact_ready)<<2|int(request.contact_allowed)<<3
        values.extend((self.core_epoch,flags))
        for v in (request.ir_raw or 0.,*request.references):
            w=word(v);values.extend((w&0xffffffff,w>>32))
        return values

    def sample(self,request):
        if self.closed or self.fault or not self.epoch or self.mode_b is not True:
            raise RuntimeError('continuous driver closed/locked/not initialized in B: '+self.fault)
        try:
            self._validate(request);values=self._encode(request)
            self._begin()
            for i,v in enumerate(values):self._write(0x40+i*4,v)
            self._write(8,2);status=self._poll()
            if (status&48!=48 or self._read(24)!=self.core_epoch or self._read(28)!=2 or
                [self._read(0xa0+i*4) for i in range(22)]!=values):
                raise RuntimeError('continuous result identity/mode/payload differs')
            raw,mean,candidate,joint,mix=(self._float(i) for i in range(192,197))
            nstatus=self._read64(197)
            def signed32(index):
                v=self._read64(index);lo=v&0xffffffff
                signed=lo-(1<<32) if lo>>31 else lo
                if signed&((1<<64)-1)!=v:raise RuntimeError('continuous NLMS integer not canonical')
                return signed
            candidate_int,output_int=signed32(198),signed32(199)
            if nstatus>15 or nstatus&8 or bool(nstatus&1)!=request.valid or candidate!=candidate_int/65536:
                raise RuntimeError('continuous original NLMS state/status differs')
            reason=self._read64(205);checked=self._read64(206);protection=self._read64(207)
            if reason>=len(REASONS) or checked>1 or protection>1 or mix not in (0.,.2,.4,.6,.8,1.):
                raise RuntimeError('continuous fusion state invalid')
            branches={}
            if request.valid:
                for i,name in enumerate(BRANCHES):
                    base=32+32*i
                    count,last,bpm_valid,peak=(self._read64(base+j) for j in (14,12,21,22))
                    if count>5 or any(v>1 for v in (last,bpm_valid,peak)):
                        raise RuntimeError('continuous bounded branch flags/count differ')
                    ibis=tuple(self._float(base+15+j) for j in range(count))
                    branches[name]=BranchResult(self._float(base+23),bool(peak),
                        self._float(base+20) if bpm_valid else None,ibis,self._read64(base+9),
                        self._read64(base+10) if last else None,self._float(base+11) if last else None,self._read64(base+13))
            from heart_v3a.axi_contract import NlmsReply
            reply=NlmsReply(request.identity.sequence,self.epoch,request.beta_int,candidate_int,output_int,nstatus,0)
            self._ack();elapsed=self._time()-self.started
            self.previous=(request.identity,request.valid);self.next_sequence+=1;self.counts['sample']+=1;self._reply=reply
            return SampleResult(request.identity,self.core_epoch,raw if request.valid else None,
                mean if request.valid else None,reply,joint if request.valid else None,mix,REASONS[reason],
                bool(protection),bool(checked),branches,elapsed)
        except BaseException as exc:
            if not self.fault:self.fault=str(exc) or type(exc).__name__
            raise

    def close(self):
        if self.closed:return dict(cleanup_complete=True,already_closed=True,original_fault=self.fault)
        self.deadline=None
        try:
            self._begin();self._write(8,8)
            while True:
                status=self._read(12);control=self._read(52)
                if status&8 and status&64 and not status&3 and control&16:break
            self.closed=True
            return dict(cleanup_complete=True,quiescent=True,original_fault=self.fault)
        except BaseException as exc:
            return dict(cleanup_complete=False,quiescent=False,original_fault=self.fault,
                cleanup_error=dict(type=type(exc).__name__,message=str(exc)))
