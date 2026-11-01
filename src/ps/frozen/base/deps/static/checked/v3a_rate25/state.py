"""25 Hz motion/quality windows, retaining the original threshold meanings."""
from collections import deque, OrderedDict
import numpy as np

from heart_v2.runtime_state import MotionState, QualityState
from heart_v3a.live.statistics_fast import CachedBranchQuality
from .policy import HISTORY, CHECK_EVERY, MOTION_WINDOW, PERIOD_LAGS, peak_fresh


class Motion25:
    def __init__(self):
        self.window = deque(maxlen=MOTION_WINDOW)
        self.label = None

    def step(self, axes):
        axes = np.asarray(axes,float)
        if axes.shape != (3,) or not np.isfinite(axes).all():
            raise ValueError('运动输入必须为三个有限数')
        self.window.append(float(axes @ axes))
        if len(self.window) < MOTION_WINDOW:
            return MotionState(None,False,None,'等待运动状态历史')
        rms = float(np.sqrt(np.mean(self.window)))
        if self.label is None:
            self.label = 'static' if rms < .03 else 'heavy' if rms >= .15 else 'light'
        elif self.label == 'static':
            if rms >= .18: self.label = 'heavy'
            elif rms > .036: self.label = 'light'
        elif self.label == 'heavy':
            if rms <= .024: self.label = 'static'
            elif rms < .12: self.label = 'light'
        elif rms <= .024: self.label = 'static'
        elif rms >= .18: self.label = 'heavy'
        return MotionState(self.label,True,rms,'')


class QualityCache25:
    def __init__(self):
        self.entries = OrderedDict()

    def get(self,values):
        if values.shape != (HISTORY,) or not np.isfinite(values).all():
            raise ValueError('25Hz质量统计需要100个有限数')
        key = values.tobytes()
        if key not in self.entries:
            centered = values-values.mean()
            periodicity = 0.
            for lag in PERIOD_LAGS:
                left,right = centered[:-lag],centered[lag:]
                norm = np.sqrt((left @ left)*(right @ right))
                if norm > 0:
                    periodicity = max(periodicity,float((left @ right)/norm))
            amplitude = float(np.percentile(values,95)-np.percentile(values,5))
            self.entries[key] = amplitude,min(1.,periodicity)
            if len(self.entries) > 4:
                self.entries.popitem(last=False)
        self.entries.move_to_end(key)
        return self.entries[key]


class BranchQuality25(CachedBranchQuality):
    # Only reuse rate-independent IBI-CV caching, not the 50 Hz step function.
    def __init__(self,window_cache=None):
        super().__init__(window_cache if window_cache is not None else QualityCache25())

    def reset(self):
        super().reset()
        self.window = deque(maxlen=HISTORY)

    def step(self,filtered_counts,*,peak,ibis,allowed=True):
        if not allowed or not np.isfinite(filtered_counts):
            self.reset()
            return QualityState('bad',False,None,None,None,'接触许可未就绪／波形无效')
        self.count += 1
        self.window.append(float(filtered_counts))
        if peak: self.last_peak_count = self.count
        if len(self.window) < HISTORY:
            return QualityState('bad',False,None,None,None,'等待质量统计窗口')
        if self.amplitude is None or self.count % CHECK_EVERY == 0:
            self.amplitude,self.periodicity = self.window_cache.get(np.asarray(self.window))
        cv = self._interval_cv(ibis)
        if cv is None:
            return QualityState('bad',False,self.amplitude,self.periodicity,None,'等待至少两个有效峰间隔')
        age = None if self.last_peak_count is None else self.count-self.last_peak_count
        if not peak_fresh(age): label,reason = 'bad','有效峰值过期'
        elif self.amplitude < 100: label,reason = 'bad','脉搏幅值不足'
        elif self.periodicity < .25: label,reason = 'bad','周期性不足'
        elif cv > .30: label,reason = 'bad','峰间隔不稳定'
        elif self.periodicity >= .5 and cv <= .15: label,reason = 'good','质量优'
        else: label,reason = 'medium','质量中'
        return QualityState(label,True,self.amplitude,self.periodicity,cv,reason)
