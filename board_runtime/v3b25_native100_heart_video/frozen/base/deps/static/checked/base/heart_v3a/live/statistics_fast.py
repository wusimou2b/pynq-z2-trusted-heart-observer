"""live专用等价统计：同序归约、同输入有界缓存；不改变决策频率。"""
from collections import OrderedDict
from types import MethodType

import numpy as np

from heart_v2.metrics import _matching_vectors, _validate_max_lag
from heart_v2.runtime_state import BranchQuality, QualityState
from heart_v3a.runtime_pl_chain import RuntimePlMainChain
from . import history_fast, numpy_compat
from .single_sample import ScalarSosHeartRateDetector


class _LeanWindowMetrics(history_fast._WindowMetrics):
    def __init__(self):
        super().__init__()
        self.parts = {}

    def _parts(self, values, key, maximum):
        cache_key = key, maximum
        if cache_key not in self.parts:
            n = len(values)
            limit = min(maximum, n-2)
            parts = []
            for lag in range(-limit, limit+1):
                part = values[:n+lag] if lag < 0 else values[lag:]
                # 已由入口转换为一维float64。与ndarray.mean相同的归约、除法；
                # 保留原切片stride，不改为前缀和、批量矩阵归约或近似。
                centered = part - np.add.reduce(part, axis=None)/len(part)
                # centered为连续实数一维数组；原norm也是dot自身再sqrt。
                parts.append((centered, np.sqrt(centered.dot(centered))))
            self.parts[cache_key] = parts
        return self.parts[cache_key]

    def correlation(self, output, reference_signal, max_lag):
        max_lag = _validate_max_lag(max_lag)
        output, reference_signal = _matching_vectors(output, reference_signal)
        if not (np.isfinite(output).all() and np.isfinite(reference_signal).all()):
            raise ValueError('correlation inputs must contain only finite values')
        output_key, reference_key = self._key(output), self._key(reference_signal)
        key = output_key, reference_key, max_lag
        if key not in self.correlations:
            ys = self._parts(output, output_key, max_lag)
            xs = self._parts(reference_signal, reference_key, max_lag)
            scores = []
            for (y, y_norm), (x, x_norm) in zip(ys, reversed(xs)):
                denominator = y_norm*x_norm
                scores.append(0.0 if denominator == 0 else abs(float(y @ x / denominator)))
            self.correlations[key] = max(scores, default=0.0)
        return self.correlations[key]


def assess_history(raw, candidate, magnitude, axes, actual):
    window = _LeanWindowMetrics()
    metric = numpy_compat._bind(numpy_compat.aligned_metrics,
        max_abs_correlation=window.correlation, band_power=window.power)
    assess = numpy_compat._bind(numpy_compat.assess_history, aligned_metrics=metric)
    return assess(raw, candidate, magnitude, axes, actual)


class LeanJointBenefitSelector(history_fast.FastJointBenefitSelector):
    step = numpy_compat._bind(history_fast.FastJointBenefitSelector.step, assess_history=assess_history)


runtime_step = numpy_compat._bind(RuntimePlMainChain.step, JointBenefitSelector=LeanJointBenefitSelector)


def window_periodicity(values):
    centered = np.array(values, dtype=float, copy=True)
    if centered.shape != (200,) or not np.isfinite(centered).all():
        raise ValueError('周期性计算需要完整的 200 个有限样本')
    centered -= centered.mean()
    scores = [0.]
    for lag in range(15, 76):
        left, right = centered[:-lag], centered[lag:]
        denominator = np.sqrt(left.dot(left)*right.dot(right))
        scores.append(float(left.dot(right)/denominator) if denominator > 0 else 0.)
    return float(np.clip(max(scores), 0., 1.))


class QualityWindowCache:
    """最多保存四个完整窗口的纯计算结果；不存状态/标签/峰龄。"""
    def __init__(self):
        self.entries = OrderedDict()

    def get(self, values):
        key = values.shape, values.dtype.str, values.tobytes()
        if key not in self.entries:
            amplitude = float(np.percentile(values,95)-np.percentile(values,5))
            self.entries[key] = amplitude, window_periodicity(values)
            if len(self.entries) > 4:
                self.entries.popitem(last=False)
        self.entries.move_to_end(key)
        return self.entries[key]


class CachedBranchQuality(BranchQuality):
    def __init__(self, window_cache=None):
        self.window_cache = window_cache if window_cache is not None else QualityWindowCache()
        super().__init__()

    def reset(self):
        super().reset()
        self._interval_key = None
        self._cv = None

    def _interval_cv(self, ibis):
        intervals = np.asarray(tuple(ibis), dtype=float)
        key = intervals.shape, intervals.tobytes()
        if key != self._interval_key:
            if intervals.ndim != 1 or len(intervals) < 2 or not np.isfinite(intervals).all() or np.any(intervals <= 0):
                cv = None
            else:
                cv = float(np.std(intervals)/np.mean(intervals))
            self._interval_key, self._cv = key, cv
        return self._cv

    def step(self, filtered_counts, *, peak, ibis, allowed=True, reset=False):
        if reset:
            self.reset()
        if not allowed or not np.isfinite(filtered_counts):
            self.reset()
            return QualityState('bad',False,None,None,None,
                '接触许可未就绪' if not allowed else '波形无效')
        self.count += 1
        self.window.append(float(filtered_counts))
        if peak:
            self.last_peak_count = self.count
        if len(self.window) < 200:
            return QualityState('bad',False,None,None,None,'等待质量统计窗口')
        if self.amplitude is None or self.count % 10 == 0:
            self.amplitude, self.periodicity = self.window_cache.get(np.asarray(self.window))
        cv = self._interval_cv(ibis)
        if cv is None:
            return QualityState('bad',False,self.amplitude,self.periodicity,None,'等待至少两个有效峰间隔')
        # 即使IBI和窗口统计复用，峰龄/状态每拍重新计算，不能缓存label。
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
        return QualityState(label,True,self.amplitude,self.periodicity,cv,reason)


class _DetectorStatistics:
    """每个判峰器私有；原step代码只调用这三个NumPy入口。"""
    def __init__(self):
        self.cache = {}

    def _get(self, name, key, value):
        saved = self.cache.get(name)
        if saved is None or saved[0] != key:
            saved = key, getattr(np,name)(value)
            self.cache[name] = saved
        return saved[1]

    def floor(self, value):
        return self._get('floor',value,value)

    def ceil(self, value):
        return self._get('ceil',value,value)

    def median(self, values):
        return self._get('median',tuple(values),values)


class CachedSosHeartRateDetector(ScalarSosHeartRateDetector):
    def __init__(self, *args, **kwargs):
        self._statistics = _DetectorStatistics()
        super().__init__(*args, **kwargs)
        # 原SOS/判峰step的code对象和计算顺序不变；不改全局NumPy。
        self.step = MethodType(numpy_compat._bind(ScalarSosHeartRateDetector.step,
            np=self._statistics),self)

    def reset(self):
        super().reset()
        self._statistics.cache.clear()
