"""因果四参考联合选择器：固定规则，不保证未来样本安全。"""
from collections import deque
from dataclasses import dataclass, fields
import numpy as np
from .aligned_metrics import aligned_metrics, VERSION

POLICY=dict(sample_rate_hz=50,history_samples=200,check_every_samples=10,
    minimum_improvement_db=1.,minimum_rms_ratio=.4,minimum_power_ratio=.5,
    numerical_power_floor=1e-12,nonworsening_tolerance_db=1e-12,
    correlation_lag_samples=10,enter_checks=2,mix_step=.1,cooldown_samples=50,
    metric_version=VERSION,actual_protection_immediate_exit=True,
    actual_protection_preserves_history=True)


@dataclass(frozen=True)
class HistoryAssessment:
    reason: str
    candidate_allowed: bool
    immediate_bypass: bool
    candidate_gains: np.ndarray
    actual_gains: np.ndarray
    active_axes: np.ndarray
    reference_energy: np.ndarray
    candidate_rms_ratio: float
    candidate_power_ratio: float
    actual_rms_ratio: float
    actual_power_ratio: float
    candidate_finite: bool
    actual_finite: bool


def assess_history(raw,candidate,magnitude,axes,actual):
    raw,candidate,magnitude,actual=[np.asarray(v,float) for v in (raw,candidate,magnitude,actual)]
    axes=np.asarray(axes,float)
    if raw.ndim!=1 or any(v.shape!=raw.shape for v in (candidate,magnitude,actual)) or axes.shape!=(len(raw),3):
        raise ValueError('history requires matching vectors and (n,3) axes')
    refs=np.column_stack([magnitude,axes])
    with np.errstate(over='ignore',invalid='ignore'):
        energies=np.mean(refs**2,axis=0) if len(raw) else np.full(4,np.nan)
        raw_energy=np.mean(raw**2) if len(raw) else np.nan
    active=np.isfinite(energies[1:]) & (energies[1:]>1e-12)
    cm=aligned_metrics(candidate,raw,magnitude); am=aligned_metrics(actual,raw,magnitude)
    cg=np.full(4,np.nan); ag=np.full(4,np.nan)
    cg[0]=cm.motion_leakage_reduction_db; ag[0]=am.motion_leakage_reduction_db
    for j in np.flatnonzero(active):
        cg[j+1]=aligned_metrics(candidate,raw,axes[:,j]).motion_leakage_reduction_db
        ag[j+1]=aligned_metrics(actual,raw,axes[:,j]).motion_leakage_reduction_db
    required=np.r_[True,active]
    immediate=False
    if len(raw)<200: reason='history_short'
    elif not np.isfinite(raw).all() or not np.isfinite(refs).all() or not np.isfinite(energies).all() or not np.isfinite(raw_energy):
        reason='nonfinite_window'
    elif not am.finite or am.output_rms_ratio<.4 or am.pulse_band_power_ratio<.5:
        reason='actual_amplitude_power_protection'; immediate=True
    elif np.any(ag[required]<-1e-12) or not np.isfinite(ag[required]).all():
        reason='actual_gain_protection'; immediate=True
    elif raw_energy<=1e-12 or energies[0]<=1e-12: reason='degenerate_reference_or_ppg'
    elif not active.any(): reason='no_active_axes'
    elif not cm.finite or not np.isfinite(cg[required]).all(): reason='nonfinite_candidate'
    elif cm.output_rms_ratio<.4: reason='poor_rms'
    elif cm.pulse_band_power_ratio<.5: reason='poor_power'
    elif cg[0]<1.: reason='insufficient_magnitude_benefit'
    elif np.any(cg[1:][active]<-1e-12): reason='candidate_axis_worsening'
    else: reason='benefit_confirmed'
    return HistoryAssessment(reason,reason=='benefit_confirmed',immediate,cg,ag,active,energies,
        cm.output_rms_ratio,cm.pulse_band_power_ratio,am.output_rms_ratio,am.pulse_band_power_ratio,
        cm.finite,am.finite)


@dataclass(frozen=True)
class JointState:
    output: float
    mix: float
    requested: bool
    checked: bool
    reason: str
    candidate_gains: np.ndarray
    actual_gains: np.ndarray
    active_axes: np.ndarray
    reference_energy: np.ndarray
    rms_ratio: float
    power_ratio: float
    actual_rms_ratio: float
    actual_power_ratio: float
    candidate_finite: bool
    actual_finite: bool
    candidate_allowed: bool
    protection_triggered: bool
    window_start: int
    window_stop: int
    transition: bool
    cooldown_until: int
    good_checks: int
    history_size: int
    switch_delta: float

    @property
    def improvement_db(self): return self.candidate_gains[...,0]

    @property
    def actual_improvement_db(self): return self.actual_gains[...,0]


class JointBenefitSelector:
    def __init__(self):
        self.index=0
        self._clear()

    def _clear(self):
        self.history=deque(maxlen=200)
        self.good_checks=0; self.requested=False; self.mix=0.; self.cooldown_until=-1
        self.reason='history_short'; self.assessment=None
        self.window_start=self.window_stop=-1

    def step(self,raw,candidate,magnitude,axes,valid=True,contact_allowed=True,reset=False,clipped=False):
        values=np.asarray([raw,candidate,magnitude],float); axes=np.asarray(axes,float)
        if values.shape!=(3,) or axes.shape!=(3,): raise ValueError('step requires scalars and three axes')
        previous=self.requested; previous_mix=self.mix
        if reset: self._clear()
        blocked=('invalid' if not valid else 'contact_blocked' if not contact_allowed else
            'model_clipped' if clipped else 'nonfinite' if not np.isfinite(values).all() or not np.isfinite(axes).all() else '')
        checked=False; protection=False
        if blocked:
            self._clear(); self.reason=blocked
            output=float(raw) if valid and np.isfinite(raw) else 0.
        else:
            if len(self.history)==200 and self.index%10==0:
                checked=True
                h=np.asarray(self.history,float)
                a=assess_history(h[:,1],h[:,2],h[:,3],h[:,4:7],h[:,7])
                self.assessment=a; self.reason=a.reason
                self.window_start=int(h[0,0]); self.window_stop=int(h[-1,0])+1
                if a.immediate_bypass:
                    if self.requested or self.mix>0:
                        # 已开始正常缓退时，实际保护不能反复延长同一次退出的冷却。
                        if self.requested or self.cooldown_until<0:
                            self.cooldown_until=self.index+50
                    self.requested=False; self.good_checks=0; self.mix=0.; protection=True
                elif not a.candidate_allowed:
                    if self.requested: self.cooldown_until=self.index+50
                    self.requested=False; self.good_checks=0
                elif self.index<self.cooldown_until:
                    self.requested=False; self.good_checks=0; self.reason='cooldown'
                else:
                    self.good_checks+=1
                    self.requested=self.good_checks>=2
            if self.index<self.cooldown_until:
                self.requested=False; self.good_checks=0
            self.mix=round(min(1.,self.mix+.1) if self.requested else max(0.,self.mix-.1),10)
            output=(1-self.mix)*float(raw)+self.mix*float(candidate)
            self.history.append((self.index,float(raw),float(candidate),float(magnitude),*axes,output))
        a=self.assessment
        # 当前输入的纯混合系数切换增量；重置也明确记录。
        delta=(self.mix-previous_mix)*(float(candidate)-float(raw)) if np.isfinite(values[:2]).all() else np.nan
        state=JointState(output,self.mix,self.requested,checked,self.reason,
            a.candidate_gains.copy() if a else np.full(4,np.nan),
            a.actual_gains.copy() if a else np.full(4,np.nan),
            a.active_axes.copy() if a else np.zeros(3,bool),
            a.reference_energy.copy() if a else np.full(4,np.nan),
            a.candidate_rms_ratio if a else np.nan,a.candidate_power_ratio if a else np.nan,
            a.actual_rms_ratio if a else np.nan,a.actual_power_ratio if a else np.nan,
            a.candidate_finite if a else False,a.actual_finite if a else False,
            a.candidate_allowed if a else False,protection,self.window_start,self.window_stop,
            previous!=self.requested,self.cooldown_until,self.good_checks,len(self.history),delta)
        self.index+=1
        return state


def replay(raw,candidate,magnitude,axes,valid=None,contact_allowed=None,reset=None,clipped=None):
    raw,candidate,magnitude=[np.asarray(v,float) for v in (raw,candidate,magnitude)]
    axes=np.asarray(axes,float)
    if raw.ndim!=1 or candidate.shape!=raw.shape or magnitude.shape!=raw.shape or axes.shape!=(len(raw),3):
        raise ValueError('replay requires matching vectors and (n,3) axes')
    n=len(raw)
    masks=[np.full(n,default,bool) if v is None else np.asarray(v,bool)
        for v,default in [(valid,True),(contact_allowed,True),(reset,False),(clipped,False)]]
    if any(v.shape!=(n,) for v in masks): raise ValueError('invalid selector masks')
    selector=JointBenefitSelector(); arrays={f.name:[] for f in fields(JointState)}
    for i in range(n):
        s=selector.step(raw[i],candidate[i],magnitude[i],axes[i],*[v[i] for v in masks])
        for name in arrays: arrays[name].append(getattr(s,name))
    types={name:bool for name in ['requested','checked','candidate_finite','actual_finite',
        'candidate_allowed','protection_triggered','transition','active_axes']}
    types.update({name:np.int64 for name in ['window_start','window_stop','cooldown_until','good_checks','history_size']})
    types['reason']=str
    result={name:np.asarray(v,dtype=types.get(name,float)) for name,v in arrays.items()}
    for name,width in [('active_axes',3),('candidate_gains',4),('actual_gains',4),('reference_energy',4)]:
        result[name]=result[name].reshape(n,width)
    return JointState(**result)
