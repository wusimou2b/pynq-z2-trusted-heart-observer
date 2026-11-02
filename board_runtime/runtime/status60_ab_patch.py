"""Owner-local A3-R/C-E policy. Imported only after the original bootstrap."""
from collections import deque
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass, fields, replace, asdict
import math
from numbers import Integral
import time

from effective25.capture import Capture25 as OriginalCapture25, reconstruct_timestamps
from effective25.frontend import Frontend25 as OriginalFrontend25, Supervisor25 as OriginalSupervisor25
from effective25.safety import Safety25 as OriginalSafety25
from effective25.session import SupervisedSource25 as OriginalSupervisedSource25
from heart_axi_live import pack_sample
from heart_v2.runtime_main_chain import Observation, _validated_observation
from heart_v3a.live.capture import phase_at
from heart_v3a.live.contracts import LiveRecord, LiveBatch, plain
from effective25.policy import ACCEL_REPEAT_LIMIT

PAIR_POLICY = 'a3r_causal_reuse80_v1'
CLOCK_POLICY = 'ce_fifo_count_host80_v1'
PERIOD_NS = 40_000_000
AGE_NS = ERROR_NS = 80_000_000
HOST_LIMIT_NS = 500_000_000
WINDOW_NS = 2_000_000_000
ANCHORS = 128
AUDIT_CAPACITY = 4096


class AuditOverflow(RuntimeError):
    pass


class BoundedAudit(list):
    def __init__(self):
        super().__init__(); self.overflow = False

    def append(self, row):
        if len(self) >= AUDIT_CAPACITY:
            self.overflow = True
            raise AuditOverflow('a3c audit capacity exceeded')
        super().append(row)


def integer(value, name, minimum=0, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, Integral) or value < minimum
            or maximum is not None and value > maximum):
        raise ValueError('invalid integer: ' + name)
    return int(value)


@dataclass(frozen=True)
class AcquisitionContext25:
    run_epoch: str
    manifest_sha256: str
    config_identity_sha256: str
    pairing_policy_version: str
    clock_policy_version: str


def validate_context(context):
    if not isinstance(context, AcquisitionContext25):
        raise ValueError('acquisition context required')
    for value, size in [(context.run_epoch,32),(context.manifest_sha256,64),(context.config_identity_sha256,64)]:
        if not isinstance(value,str) or len(value)!=size or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('context identity encoding differs')
    if (context.pairing_policy_version,context.clock_policy_version)!=(PAIR_POLICY,CLOCK_POLICY):
        raise ValueError('context policy differs')


@dataclass(frozen=True)
class StartupAnchor25:
    context: AcquisitionContext25
    wr: int
    rd: int
    n_discarded: int
    available: int
    overflow_before_discard: int
    read_completed_ns: int


@dataclass(frozen=True)
class BatchEvidence25:
    startup: StartupAnchor25
    batch_id: int
    first_sequence: int
    n: int
    available: int
    wr: int
    rd: int
    overflow: int
    cumulative_before: int
    cumulative_after: int
    loop_started_ns: int
    read_completed_ns: int
    current_batch_mpu_read_ns: int
    original_error: str
    original_pl_fifo_ok: bool


@dataclass(frozen=True)
class ContinuityEvidence25:
    batch: BatchEvidence25
    offset: int


@dataclass(frozen=True)
class ContinuityDecision25:
    accepted: bool
    batch_id: int
    host_gap_ns: int
    host_gap_accepted_with_evidence: bool
    left_anchor_read_ns: int
    left_anchor_count: int
    count_host_error_ns: int
    failure_reason: str


@dataclass(frozen=True, kw_only=True)
class EvidenceObservation25(Observation):
    continuity: ContinuityEvidence25


@dataclass(frozen=True, kw_only=True)
class EvidenceLiveRecord25(LiveRecord):
    continuity: ContinuityEvidence25

    def to_observation(self):
        if not isinstance(self.continuity, ContinuityEvidence25):
            raise ValueError('record continuity missing')
        b = self.continuity.batch
        values = self.read_completed_ns, self.raw['ppg_read_completed_ns'], b.read_completed_ns
        for value in values: integer(value, 'read_ns')
        if not values[0] == values[1] == values[2]:
            raise ValueError('record_raw_batch_read_ns_mismatch')
        for name, expected in [('batch_id',b.batch_id),('fifo_batch_size',b.n),
                ('max_write_pointer',b.wr),('max_read_pointer',b.rd),('max_available',b.available),
                ('max30102_overflow',b.overflow),('sequence',b.first_sequence+self.continuity.offset)]:
            value = integer(self.raw[name], name)
            if value != expected: raise ValueError('record_batch_identity_mismatch:' + name)
        ob = LiveRecord.to_observation(self)
        return EvidenceObservation25(**{f.name:getattr(ob,f.name) for f in fields(Observation)}, continuity=self.continuity)


class ContinuityTracker25:
    def __init__(self, context):
        validate_context(context)
        self.context = context
        self.startup = self.previous = self.decision = None
        self.offset = -1
        self.count = 0
        self.anchors = deque()
        self.audit = BoundedAudit()
        self.fault = ''

    def accept(self, evidence):
        if self.fault: raise RuntimeError('continuity locked: ' + self.fault)
        try:
            return self._accept(evidence)
        except Exception as exc:
            self.fault = str(exc)
            b=getattr(evidence,'batch',None)
            try:
                self.audit.append(dict(accepted=False,batch_id=getattr(b,'batch_id',None),
                    read_completed_ns=getattr(b,'read_completed_ns',None),failure_reason=self.fault))
            except AuditOverflow:
                pass  # The overflow flag and original first fault remain visible.
            raise

    def _accept(self, evidence):
        if not isinstance(evidence,ContinuityEvidence25) or not isinstance(evidence.batch,BatchEvidence25):
            raise ValueError('batch evidence missing')
        b=evidence.batch; offset=integer(evidence.offset,'offset')
        if b.startup.context != self.context: raise ValueError('batch context differs')
        if self.previous is not None and b.batch_id == self.previous.batch_id:
            if b != self.previous or offset != self.offset+1 or offset >= b.n:
                raise ValueError('same batch facts/offset differ')
            self.offset=offset
            return self.decision
        if offset != 0: raise ValueError('first batch offset must be zero')
        if self.previous is not None and self.offset != self.previous.n-1:
            raise ValueError('previous batch was not fully consumed')
        for name in ['batch_id','first_sequence','available','wr','rd','overflow','cumulative_before',
                     'cumulative_after','loop_started_ns','read_completed_ns','current_batch_mpu_read_ns']:
            integer(getattr(b,name),name)
        integer(b.n,'batch size',1,31)
        integer(b.wr,'write pointer',0,31);integer(b.rd,'read pointer',0,31)
        if b.overflow or b.original_error or b.original_pl_fifo_ok is not True:
            raise ValueError('original FIFO/capture fault: ' + b.original_error)
        if b.n != b.available or b.n != (b.wr-b.rd)%32:
            raise ValueError('FIFO available/count differs')
        if not b.loop_started_ns <= b.read_completed_ns <= b.current_batch_mpu_read_ns:
            raise ValueError('physical read time order differs')
        if self.startup is None:
            a=b.startup
            integer(a.wr,'startup wr',0,31);integer(a.rd,'startup rd',0,31)
            integer(a.n_discarded,'startup size',1,32);integer(a.read_completed_ns,'startup time')
            integer(a.overflow_before_discard,'startup overflow',0,31)
            if a.available != a.n_discarded or (a.wr-a.rd)%32 != a.n_discarded%32:
                raise ValueError('startup snapshot differs')
            if b.batch_id != 0: raise ValueError('first batch must be zero')
            self.startup=a
            self.anchors.append((a.read_completed_ns,0))
            rd,wr,n,read = a.rd,a.wr,a.n_discarded,a.read_completed_ns
        else:
            p=self.previous
            if b.startup != self.startup or b.batch_id != p.batch_id+1:
                raise ValueError('batch/startup identity discontinuity')
            rd,wr,n,read=p.rd,p.wr,p.n,p.read_completed_ns
        if b.first_sequence != self.count or b.cumulative_before != self.count or b.cumulative_after != self.count+b.n:
            raise ValueError('formal sequence/count discontinuity')
        if b.rd != (rd+n)%32: raise ValueError('read pointer discontinuity')
        if (b.wr-wr)%32 != b.n: raise ValueError('write pointer/count discontinuity')
        gap=b.read_completed_ns-read
        if not 0 < gap <= HOST_LIMIT_NS: raise ValueError('host evidence gap exceeded')
        cutoff=b.read_completed_ns-WINDOW_NS
        while len(self.anchors)>1 and self.anchors[1][0]<=cutoff:self.anchors.popleft()
        left_time,left_count=self.anchors[0]
        error=abs((b.read_completed_ns-left_time)-(b.cumulative_after-left_count)*PERIOD_NS)
        if error>ERROR_NS: raise ValueError('count/host evidence error exceeded')
        if len(self.anchors)>=ANCHORS: raise ValueError('continuity anchor capacity exceeded')
        self.anchors.append((b.read_completed_ns,b.cumulative_after))
        self.decision=ContinuityDecision25(True,b.batch_id,gap,gap>AGE_NS,left_time,left_count,error,'')
        self.audit.append(dict(accepted=True,batch_id=b.batch_id,first_sequence=b.first_sequence,n=b.n,available=b.available,
            wr=b.wr,rd=b.rd,overflow=b.overflow,cumulative_before=b.cumulative_before,
            cumulative_after=b.cumulative_after,read_completed_ns=b.read_completed_ns,
            left_anchor_read_ns=left_time,left_anchor_count=left_count,count_host_error_ns=error,
            host_gap_ns=gap,host_gap_accepted_with_evidence=gap>AGE_NS,startup_boundary=b.batch_id==0))
        self.previous=b;self.offset=0;self.count=b.cumulative_after
        return self.decision


class RecordClock25:
    def __init__(self):self.first_sequence=self.first_host_time=None
    def project(self, ob):
        if self.first_sequence is None:self.first_sequence,self.first_host_time=ob.sequence,ob.time_s
        return replace(ob,time_s=self.first_host_time+(ob.sequence-self.first_sequence)/25.)


class ClockedSupervisor25:
    def __init__(self, context):
        self.context=context;self._delegate=OriginalSupervisor25()
        self.tracker=ContinuityTracker25(context);self.clock=RecordClock25()
        self.previous_host=self.previous_read_ns=None
    def __getattr__(self,name):return getattr(self._delegate,name)
    def fail(self,reason):self._delegate.fail(reason)
    def advance(self,observation):
        if self.fault:raise RuntimeError('candidate supervisor locked: '+self.fault)
        try:
            if not isinstance(observation,EvidenceObservation25):raise ValueError('evidence observation required')
            ob=_validated_observation(observation);b=ob.continuity.batch
            if b.startup.context!=self.context:raise ValueError('observation context differs')
            read=integer(b.read_completed_ns,'physical read time');previous=self.previous_host
            if previous and (ob.sequence<=previous.sequence or ob.time_s<=previous.time_s):
                raise ValueError('original host time/sequence repeated or reversed')
            if self.previous_read_ns is not None and read<self.previous_read_ns:
                raise ValueError('physical read time reversed')
            self.previous_host,self.previous_read_ns=ob,read
            self.tracker.accept(ob.continuity)
            _,good,reason=self._delegate.advance(self.clock.project(ob))
            return ob,good,reason
        except Exception as exc:self.fail(exc);raise


def _bind(obj,attr,context):
    state=getattr(obj,attr)
    if obj._context is not None or state.count or state.fault:
        exc=RuntimeError('context already bound or supervisor used/faulted');state.fail(exc);raise exc
    try:
        validate_context(context);new=ClockedSupervisor25(context)
        if new.context!=context:raise ValueError('constructed supervisor context differs')
        setattr(obj,attr,new);obj._context=context
    except Exception as exc:
        setattr(obj,attr,state);obj._context=None;state.fail(exc);raise


def _require(context,state,ob):
    if context is None:raise RuntimeError('candidate_context_unbound')
    if not isinstance(state,ClockedSupervisor25) or state.context!=context:
        raise RuntimeError('candidate_supervisor_binding_mismatch')
    if not isinstance(ob,EvidenceObservation25):raise TypeError('EvidenceObservation25 required')


class SampleClockFrontend25(OriginalFrontend25):
    def __init__(self):super().__init__();self._context=None
    def bind_context(self,context):_bind(self,'supervisor',context)
    def push(self,observation):
        try:_require(self._context,self.supervisor,observation)
        except Exception as exc:self.supervisor.fail(exc);raise
        return super().push(observation)
    def audit(self):
        return dict(super().audit(),fault=self.supervisor.fault,
            context_bound=self._context is not None and isinstance(self.supervisor,ClockedSupervisor25)
                          and self.supervisor.context==self._context)


class SampleClockSafety25(OriginalSafety25):
    def __init__(self):super().__init__();self._context=None
    def bind_context(self,context):
        with self._lock:_bind(self,'_supervisor',context)
    def observe(self,observation,read_ns):
        with self._lock:
            try:
                _require(self._context,self._supervisor,observation)
                if type(read_ns) is not int or read_ns!=observation.continuity.batch.read_completed_ns:
                    raise ValueError('external_batch_read_ns_mismatch')
            except Exception as exc:self._supervisor.fail(exc);raise
            return super().observe(observation,read_ns)


class BatchPairCapture25(OriginalCapture25):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self._context=self._startup_anchor=None;self._formal_count=0;self._imu_id=0
        self._imu_history=deque();self.pairing_audit=BoundedAudit();self.imu_reads=BoundedAudit()
    def bind_context(self,context):
        if self._begun or self._context is not None:raise RuntimeError('capture context already bound/started')
        validate_context(context);self._context=context
    def begin(self):
        if self._context is None:raise RuntimeError('capture context unbound')
        if self._begun:raise RuntimeError('capture begins once')
        self._begun=True;self.sensors.clear_max30102_fifo()
        b=self.sensors.read_fifo_ir_samples(timeout=.5)
        self.started_ns=self.clock.monotonic_ns();self._previous_timestamp_us=self.started_ns//1000
        self._startup_anchor=StartupAnchor25(self._context,int(b.write_pointer),int(b.read_pointer),
            len(b.ir_samples),int(b.available),int(b.overflow),self.started_ns)
        return dict(startup_discarded_samples=len(b.ir_samples),startup_overflow_count=int(b.overflow),
                    started_ns=self.started_ns,a3c_startup_anchor=asdict(self._startup_anchor))
    def _audit(self,sink,row,size):
        try:sink.append(row)
        except AuditOverflow as exc:self._make_fault('a3c_audit','audit_capacity_exceeded',size,exc)
    def read_batch(self):
        if not self._begun or self._fault or self._capture_stopped:raise RuntimeError('capture not active')
        loop_started=self.clock.monotonic_ns()
        try:ir_batch=self.sensors.read_fifo_ir_samples(timeout=.5)
        except Exception as exc:
            f=self._make_fault('max30102_fifo_read','sensor_read_exception',0,exc,unknown=True)
            return LiveBatch(self._batch_id,(),self.clock.monotonic_ns(),f)
        read_ns=self.clock.monotonic_ns();size=len(ir_batch.ir_samples)
        if not 0<size<=32:
            f=self._make_fault('max30102_fifo_read','invalid_fifo_batch_size',size)
            return LiveBatch(self._batch_id,(),read_ns,f)
        axes=None;valid=False
        try:
            axes=tuple(self.sensors.read_acceleration_raw())
            if len(axes)!=3 or any(type(v)is not int or not -32768<=v<=32767 for v in axes):
                raise ValueError('MPU加速度不是三路signed16整数')
            self._repeat_count=self._repeat_count+1 if axes==self._previous_acceleration else 1
            self._previous_acceleration=axes
            if axes==(0,0,0):self._make_fault('mpu_acceleration_read','acceleration_all_zero',size)
            elif self._repeat_count>=ACCEL_REPEAT_LIMIT:self._make_fault('mpu_acceleration_read','acceleration_repeated_suspected_stale',size)
            else:valid=True
        except Exception as exc:self._make_fault('mpu_acceleration_read','sensor_read_exception',size,exc)
        mpu_ns=self.clock.monotonic_ns()
        if ir_batch.overflow:self._make_fault('max30102_fifo_read','max30102_overflow',size)
        if self._sequence+size-1>0xffffffff:self._make_fault('sequence','sequence_range_exhausted',size)
        try:stamps,nominal,policy=reconstruct_timestamps(size,read_ns//1000,self._previous_timestamp_us)
        except ValueError as exc:
            stamps,nominal,policy=('',)*size,('',)*size,'invalid_observation_interval'
            self._make_fault('timestamp_reconstruction','timestamp_reconstruction_error',size,exc)
        loopback=''
        if valid and self._fault is None:
            packet=pack_sample(self._sequence+size-1,stamps[-1],int(ir_batch.ir_samples[-1]),*axes)
            try:
                loopback=self.fifo.round_trip(packet)==packet
                if not loopback:self._make_fault('axi_fifo_loopback','pl_fifo_error',size)
            except Exception as exc:
                loopback=False;self._make_fault('axi_fifo_loopback','pl_fifo_error',size,exc)
        loop_ns=self.clock.monotonic_ns()-loop_started
        current=dict(imu_read_id=self._imu_id,batch_id=self._batch_id,read_ns=mpu_ns,
                     axes=axes,repeat_count=self._repeat_count,valid=valid,total_source_uses=1 if valid else 0,extra_used=False)
        self._imu_id+=1
        self._audit(self.imu_reads,current,size)
        evidence=BatchEvidence25(self._startup_anchor,self._batch_id,self._sequence,size,int(ir_batch.available),
            int(ir_batch.write_pointer),int(ir_batch.read_pointer),int(ir_batch.overflow),self._formal_count,
            self._formal_count+size,loop_started,read_ns,mpu_ns,self._fault.reason if self._fault else '',loopback is not False)
        records=[];used=set()
        for i,ir in enumerate(ir_batch.ir_samples):
            newest=i==size-1;target=stamps[i]*1000 if stamps[i]!='' else None
            selected=current if newest and valid else None
            if not newest and valid and self._fault is None and target is not None:
                eligible=[h for h in self._imu_history if h['valid'] and not h['extra_used']
                    and h['imu_read_id'] not in used and 0<=target-h['read_ns']<=AGE_NS]
                if eligible:
                    selected=max(eligible,key=lambda h:(h['read_ns'],h['imu_read_id']))
                    selected['extra_used']=True;selected['total_source_uses']+=1
            paired=selected is not None
            if paired:used.add(selected['imu_read_id'])
            g=tuple(v/16384 for v in selected['axes']) if paired else ('','','')
            relative=(stamps[i]-self.started_ns//1000)/1e6 if target is not None else ''
            phase,index,elapsed=phase_at(self.protocol,relative) if relative!='' else ('','','')
            raw_axes=selected['axes'] if paired else axes if newest and axes is not None and len(axes)==3 else ('','','')
            source_ns=selected['read_ns'] if paired else mpu_ns
            row=dict(sequence=self._sequence,timestamp_us=stamps[i],read_timestamp_us=read_ns//1000,
                nominal_timestamp_us=nominal[i],timestamp_policy=policy,time_s=relative,ir_raw=int(ir),
                ax_g=g[0],ay_g=g[1],az_g=g[2],pair_ok=paired,accel_valid=paired,
                mpu_ax_raw=raw_axes[0],mpu_ay_raw=raw_axes[1],mpu_az_raw=raw_axes[2],
                accel_repeat_count=selected['repeat_count'] if paired else self._repeat_count if newest else '',
                fifo_batch_size=size,max30102_overflow=int(ir_batch.overflow),pl_fifo_ok=loopback if newest else '',
                error=self._fault.reason if self._fault else '',phase=phase,phase_index=index,phase_elapsed_s=elapsed,
                batch_id=self._batch_id,max_write_pointer=int(ir_batch.write_pointer),max_read_pointer=int(ir_batch.read_pointer),
                max_available=int(ir_batch.available),ppg_read_completed_ns=read_ns,mpu_read_completed_ns=source_ns,capture_loop_ns=loop_ns)
            delta=selected['read_ns']-target if paired and target is not None else None
            self._audit(self.pairing_audit,dict(sequence=self._sequence,batch_id=self._batch_id,latest_in_batch=newest,
                paired=paired,imu_read_id=selected['imu_read_id'] if paired else None,
                source_batch_id=selected['batch_id'] if paired else None,source_read_ns=selected['read_ns'] if paired else None,
                current_batch_mpu_read_ns=mpu_ns,target_ns=target,pair_delta_ns=delta,
                age_ns=-delta if paired and not newest else None,reused=paired and not newest,
                total_source_uses=selected['total_source_uses'] if paired else 0,
                rejection_reason='' if paired else 'no_eligible_causal_source_or_current_invalid'),size)
            records.append(EvidenceLiveRecord25(row,read_ns,continuity=ContinuityEvidence25(evidence,i)))
            self._sequence+=1
        self._formal_count+=size
        if valid:self._imu_history.append(current)
        if stamps[-1]!='':
            self._previous_timestamp_us=stamps[-1]
            while self._imu_history and self._imu_history[0]['read_ns']<stamps[-1]*1000-AGE_NS:self._imu_history.popleft()
        while len(self._imu_history)>32:self._imu_history.popleft()
        result=LiveBatch(self._batch_id,tuple(records),self.clock.monotonic_ns(),self._fault)
        self._batch_id+=1;return result


class EvidenceSource25(OriginalSupervisedSource25):
    def read_batch(self):
        batch=self.source.read_batch()
        if batch.fault is not None:
            f=batch.fault;self.session._fail(f.stage,f.reason,f.sequence,plain(f.details))
        for record in batch.records:
            try:self.session._safety.observe(record.to_observation(),record.read_completed_ns)
            except Exception as exc:
                self.session._fail('raw_safety',str(exc),record.raw['sequence']);break
        if batch.records:
            with self.session._lock:self.session._overruns25+=int(batch.records[0].raw['capture_loop_ns']>PERIOD_NS)
        return batch


@contextmanager
def install_patches():
    from effective25 import capture,frontend,safety,session
    changes=[(capture,'Capture25',BatchPairCapture25),(frontend,'Frontend25',SampleClockFrontend25),
             (session,'Frontend25',SampleClockFrontend25),(safety,'Safety25',SampleClockSafety25),
             (session,'Safety25',SampleClockSafety25),(session,'SupervisedSource25',EvidenceSource25)]
    old=[(module,name,getattr(module,name)) for module,name,_ in changes]
    try:
        for module,name,value in changes:setattr(module,name,value)
        yield
    finally:
        for module,name,value in reversed(old):setattr(module,name,value)
