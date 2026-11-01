"""V2 固定工程阈值的运动与质量状态；不读取实验标签。"""
from collections import deque
from dataclasses import dataclass

import numpy as np


MOTION_POLICY = dict(window_samples=50, static_threshold_g=.03,
                     heavy_threshold_g=.15, hysteresis_fraction=.2)
QUALITY_POLICY = dict(window_samples=200, check_every_samples=10,
    minimum_amplitude_counts=100., minimum_periodicity=.25,
    good_periodicity=.5, maximum_ibi_cv=.30, good_ibi_cv=.15,
    minimum_ibi_count=2, maximum_peak_age_samples=75,
    periodicity_lag_min=15, periodicity_lag_max=75)


@dataclass(frozen=True)
class MotionState:
    label: str | None
    ready: bool
    rms_g: float | None
    reason_cn: str


@dataclass(frozen=True)
class QualityState:
    label: str
    ready: bool
    amplitude_counts: float | None
    periodicity: float | None
    ibi_cv: float | None
    reason_cn: str


def window_periodicity(values):
    centered = np.array(values, dtype=float, copy=True)
    if centered.shape != (200,) or not np.isfinite(centered).all():
        raise ValueError('周期性计算需要完整的 200 个有限样本')
    centered -= centered.mean()
    scores = [0.]
    for lag in range(15, 76):
        left, right = centered[:-lag], centered[lag:]
        denominator = np.sqrt(np.dot(left, left)*np.dot(right, right))
        scores.append(float(np.dot(left, right)/denominator) if denominator > 0 else 0.)
    return float(np.clip(max(scores), 0., 1.))


class MotionClassifier:
    def __init__(self):
        self.reset()

    def reset(self):
        self.window = deque(maxlen=50)
        self.label = None

    def step(self, dynamic_axes_g, *, valid=True, reset=False):
        if reset:
            self.reset()
        axes = np.asarray(dynamic_axes_g, dtype=float)
        if not valid or axes.shape != (3,) or not np.isfinite(axes).all():
            self.reset()
            return MotionState(None, False, None, '加速度无效／等待连续样本')
        self.window.append(float(np.dot(axes, axes)))
        if len(self.window) < 50:
            return MotionState(None, False, None, '等待运动状态历史')
        rms = float(np.sqrt(np.mean(self.window)))
        if self.label is None:
            self.label = 'static' if rms < .03 else 'heavy' if rms >= .15 else 'light'
        elif self.label == 'static':
            if rms >= .18:
                self.label = 'heavy'
            elif rms > .036:
                self.label = 'light'
        elif self.label == 'heavy':
            if rms <= .024:
                self.label = 'static'
            elif rms < .12:
                self.label = 'light'
        elif rms <= .024:
            self.label = 'static'
        elif rms >= .18:
            self.label = 'heavy'
        return MotionState(self.label, True, rms, '')


class BranchQuality:
    def __init__(self):
        self.reset()

    def reset(self):
        self.window = deque(maxlen=200)
        self.count = 0
        self.last_peak_count = None
        self.amplitude = self.periodicity = None

    def step(self, filtered_counts, *, peak, ibis, allowed=True, reset=False):
        if reset:
            self.reset()
        if not allowed or not np.isfinite(filtered_counts):
            self.reset()
            return QualityState('bad', False, None, None, None,
                                '接触许可未就绪' if not allowed else '波形无效')
        self.count += 1
        self.window.append(float(filtered_counts))
        if peak:
            self.last_peak_count = self.count
        if len(self.window) < 200:
            return QualityState('bad', False, None, None, None, '等待质量统计窗口')
        if self.amplitude is None or self.count % 10 == 0:
            values = np.asarray(self.window)
            self.amplitude = float(np.percentile(values, 95)-np.percentile(values, 5))
            self.periodicity = window_periodicity(values)
        intervals = np.asarray(tuple(ibis), dtype=float)
        if intervals.ndim != 1 or len(intervals) < 2 or not np.isfinite(intervals).all() or np.any(intervals <= 0):
            return QualityState('bad', False, self.amplitude, self.periodicity, None, '等待至少两个有效峰间隔')
        cv = float(np.std(intervals)/np.mean(intervals))
        stale = self.last_peak_count is None or self.count-self.last_peak_count > 75
        if stale:
            label, reason = 'bad', '有效峰值过期'
        elif self.amplitude < 100:
            label, reason = 'bad', '脉搏幅值不足'
        elif self.periodicity < .25:
            label, reason = 'bad', '周期性不足'
        elif cv > .30:
            label, reason = 'bad', '峰间隔不稳定'
        elif self.periodicity >= .5 and cv <= .15:
            label, reason = 'good', '质量优'
        else:
            label, reason = 'medium', '质量中'
        return QualityState(label, True, self.amplitude, self.periodicity, cv, reason)
