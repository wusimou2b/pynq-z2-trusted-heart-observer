"""Reuse immutable input preparation, never a supervisor decision or state.

Private caches are not dataclass fields: replace()/pickle-free reconstruction
does not copy them. They live only as long as the bounded record queues.
"""
from contextlib import contextmanager
from dataclasses import dataclass, fields
import math

import status60_ab_patch as base
from heart_v2.runtime_main_chain import Observation, _validated_observation, _finite_number
from effective25.policy import MAX_GAP_SECONDS

_OBS_FIELDS=tuple(f.name for f in fields(Observation))


@dataclass(frozen=True,kw_only=True)
class ReusableObservation25(base.EvidenceObservation25):
    pass


@dataclass(frozen=True,kw_only=True)
class ReusableRecord25(base.EvidenceLiveRecord25):
    def to_observation(self):
        cached=getattr(self,'_observation',None)
        if cached is None:
            # The retained implementation verifies every raw/batch/read-time
            # equality before any reusable object is published.
            ob=super().to_observation()
            cached=ReusableObservation25(**{name:getattr(ob,name) for name in _OBS_FIELDS},
                                         continuity=ob.continuity)
            object.__setattr__(cached,'_immutable_record_input',True)
            object.__setattr__(self,'_observation',cached)
        return cached


def normalized(ob):
    if type(ob) is ReusableObservation25 and getattr(ob,'_immutable_record_input',False):
        cached=getattr(ob,'_normalized',None)
        if cached is None:
            cached=_validated_observation(ob)
            object.__setattr__(ob,'_normalized',cached)
        return cached
    # Direct/untrusted observations, including replace(ob, ...), retain the
    # full original validator on every call. Failed validation is never cached.
    return _validated_observation(ob)


class NormalizedPolicy25(base.OriginalSupervisor25):
    def advance_normalized(self,ob):
        """Original Supervisor25 policy with only duplicate input work removed.

        Only ReuseClockedSupervisor25 calls this, after the original full host
        validator and C-E checks. Projection changes time only, so revalidate
        that newly computed value. Public advance() retains its original checks.
        """
        if self.fault:
            raise RuntimeError('25Hz原始监督故障锁定：'+self.fault)
        try:
            model_time=_finite_number(ob.time_s,'时间')
            if model_time<0:raise ValueError('时间必须非负')
            previous=self.previous
            if previous and (ob.sequence<=previous.sequence or ob.time_s<=previous.time_s):
                raise ValueError('时间或序号重复／倒退')
        except Exception as exc:
            self.fail(exc);raise
        reasons=[]
        tolerance=4*math.ulp(max(ob.time_s,MAX_GAP_SECONDS))
        if previous and (ob.sequence!=previous.sequence+1
                         or ob.time_s-previous.time_s>MAX_GAP_SECONDS+tolerance):
            reasons.append('原始序号／时间缺口')
        if ob.reset:reasons.append('显式重置')
        if not ob.pair_ok or not ob.accel_valid:reasons.append('PPG／加速度未配对或无效')
        if not ob.pl_fifo_ok or ob.error.strip():reasons.append('采集／FIFO错误：'+ob.error)
        if ob.contact_ok is False:reasons.append('记录接触阻断')
        if reasons:
            self.gate.reset();contact=None
        else:
            contact=self.gate.step(ob.ir_raw,ob.contact_ok)
            if not contact.derived_contact_ok:reasons.append('原始接触异常：'+contact.reason)
            elif self.ready and not contact.trusted_allowed:reasons.append('原始脉搏幅度恢复许可撤销')
        good=not reasons
        if not good:self.generation+=1;self.ready=False
        else:self.ready=bool(contact.trusted_allowed)
        self.previous=ob;self.count+=1
        return ob,good,'；'.join(reasons)


class ReuseClockedSupervisor25(base.ClockedSupervisor25):
    def __init__(self,context):
        self.context=context;self._delegate=NormalizedPolicy25()
        self.tracker=base.ContinuityTracker25(context);self.clock=base.RecordClock25()
        self.previous_host=self.previous_read_ns=None

    def advance(self,observation):
        if self.fault:raise RuntimeError('candidate supervisor locked: '+self.fault)
        try:
            if not isinstance(observation,base.EvidenceObservation25):
                raise ValueError('evidence observation required')
            ob=normalized(observation);b=ob.continuity.batch
            if b.startup.context!=self.context:raise ValueError('observation context differs')
            read=base.integer(b.read_completed_ns,'physical read time');previous=self.previous_host
            if previous and (ob.sequence<=previous.sequence or ob.time_s<=previous.time_s):
                raise ValueError('original host time/sequence repeated or reversed')
            if self.previous_read_ns is not None and read<self.previous_read_ns:
                raise ValueError('physical read time reversed')
            self.previous_host,self.previous_read_ns=ob,read
            self.tracker.accept(ob.continuity)
            _,good,reason=self._delegate.advance_normalized(self.clock.project(ob))
            return ob,good,reason
        except Exception as exc:self.fail(exc);raise


@contextmanager
def install_reuse():
    """Owner-only, enclosing the original AB activation; restore on all exits."""
    record,supervisor=base.EvidenceLiveRecord25,base.ClockedSupervisor25
    try:
        base.EvidenceLiveRecord25=ReusableRecord25
        base.ClockedSupervisor25=ReuseClockedSupervisor25
        yield
    finally:
        base.EvidenceLiveRecord25=record
        base.ClockedSupervisor25=supervisor
