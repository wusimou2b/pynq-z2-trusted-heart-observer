"""100-point/25 Hz causal benefit assessment, a new numerical baseline."""
from collections import deque
from dataclasses import dataclass
import numpy as np
from scipy.signal import welch

from heart_v2.joint_benefit import HistoryAssessment
from heart_v3a.live.statistics_fast import _LeanWindowMetrics
from .policy import HISTORY, CHECK_EVERY, PROCESS_HZ, CORRELATION_LAG, MIX_STEP, COOLDOWN


class WindowMetrics25(_LeanWindowMetrics):
    def power(self,values):
        values = np.asarray(values,float)
        if values.shape != (HISTORY,) or not np.isfinite(values).all():
            raise ValueError('25Hz谱统计需要100个有限数')
        key = self._key(values)
        if key not in self.powers:
            f,p = welch(values,fs=PROCESS_HZ,window='hann',nperseg=HISTORY,
                        noverlap=0,nfft=HISTORY,detrend='constant',scaling='density')
            band = (f>=.7)&(f<=3.)
            # NumPy 1.21 on the board has trapz, not trapezoid.
            integrate = np.trapezoid if hasattr(np,'trapezoid') else np.trapz
            self.powers[key] = float(integrate(p[band],f[band]))
        return self.powers[key]

    def correlation(self,output,reference_signal):
        return super().correlation(output,reference_signal,CORRELATION_LAG)


def assess_history25(raw,candidate,magnitude,axes,actual):
    raw,candidate,magnitude,actual = [np.asarray(v,float) for v in (raw,candidate,magnitude,actual)]
    axes = np.asarray(axes,float)
    if any(v.shape != (HISTORY,) for v in (raw,candidate,magnitude,actual)) or axes.shape != (HISTORY,3):
        raise ValueError('25Hz收益检查需要100点和匹配的三轴')
    if not all(np.isfinite(v).all() for v in (raw,candidate,magnitude,axes,actual)):
        raise ValueError('收益窗口存在非有限数')
    refs = np.column_stack((magnitude,axes))
    energy = np.mean(refs**2,axis=0)
    raw_energy = float(np.mean(raw**2))
    active = energy[1:] > 1e-12
    required = np.r_[True,active]
    window = WindowMetrics25()
    cg,ag = np.full(4,np.nan),np.full(4,np.nan)
    for j in np.flatnonzero(required):
        original = window.correlation(raw,refs[:,j])
        for signal,gains in ((candidate,cg),(actual,ag)):
            leakage = window.correlation(signal,refs[:,j])
            gains[j] = 10*np.log10((original**2+1e-12)/(leakage**2+1e-12))
    ratios = []
    for signal in (candidate,actual):
        rms = float(np.sqrt(np.mean(signal**2))/max(np.sqrt(raw_energy),1e-12))
        power = window.power(signal)/max(window.power(raw),1e-12)
        ratios.append((rms,power))
    (cr,cp),(ar,ap) = ratios
    cf = bool(np.isfinite([cr,cp,*cg[required]]).all())
    af = bool(np.isfinite([ar,ap,*ag[required]]).all())
    immediate = False
    if not af or ar < .4 or ap < .5:
        reason,immediate = 'actual_amplitude_power_protection',True
    elif np.any(ag[required] < -1e-12):
        reason,immediate = 'actual_gain_protection',True
    elif raw_energy <= 1e-12 or energy[0] <= 1e-12: reason = 'degenerate_reference_or_ppg'
    elif not active.any(): reason = 'no_active_axes'
    elif not cf: reason = 'nonfinite_candidate'
    elif cr < .4: reason = 'poor_rms'
    elif cp < .5: reason = 'poor_power'
    elif cg[0] < 1.: reason = 'insufficient_magnitude_benefit'
    elif np.any(cg[1:][active] < -1e-12): reason = 'candidate_axis_worsening'
    else: reason = 'benefit_confirmed'
    return HistoryAssessment(reason,reason=='benefit_confirmed',immediate,cg,ag,active,energy,cr,cp,ar,ap,cf,af)


@dataclass(frozen=True)
class Joint25:
    output: float
    mix: float
    reason: str
    protection_triggered: bool
    checked: bool


class Selector25:
    def __init__(self):
        self.index = 0
        self._clear()

    def _clear(self):
        self.history = deque(maxlen=HISTORY)
        self.good_checks = 0
        self.requested = False
        self.mix = 0.
        self.cooldown_until = -1
        self.reason = 'history_short'
        self.assessment = None

    def step(self,raw,candidate,magnitude,axes,*,contact_allowed=True,clipped=False):
        values = np.asarray((raw,candidate,magnitude,*axes),float)
        if values.shape != (6,) or not np.isfinite(values).all():
            raise ValueError('收益选择器需要有限标量和三轴')
        checked = protection = False
        if not contact_allowed or clipped:
            self._clear()
            self.reason = 'contact_blocked' if not contact_allowed else 'model_clipped'
            output = float(raw)
        else:
            if len(self.history) == HISTORY and self.index % CHECK_EVERY == 0:
                checked = True
                h = np.asarray(self.history,float)
                a = assess_history25(h[:,1],h[:,2],h[:,3],h[:,4:7],h[:,7])
                self.assessment,self.reason = a,a.reason
                if a.immediate_bypass:
                    if self.requested or self.mix > 0:
                        if self.requested or self.cooldown_until < 0:
                            self.cooldown_until = self.index+COOLDOWN
                    self.requested = False
                    self.good_checks = 0
                    self.mix = 0.
                    protection = True
                elif not a.candidate_allowed:
                    if self.requested: self.cooldown_until = self.index+COOLDOWN
                    self.requested = False
                    self.good_checks = 0
                elif self.index < self.cooldown_until:
                    self.requested = False
                    self.good_checks = 0
                    self.reason = 'cooldown'
                else:
                    self.good_checks += 1
                    self.requested = self.good_checks >= 2
            if self.index < self.cooldown_until:
                self.requested = False
                self.good_checks = 0
            self.mix = round(min(1.,self.mix+MIX_STEP) if self.requested else max(0.,self.mix-MIX_STEP),10)
            output = (1-self.mix)*raw+self.mix*candidate
            self.history.append((self.index,raw,candidate,magnitude,*axes,output))
        self.index += 1
        return Joint25(float(output),self.mix,self.reason,protection,checked)
