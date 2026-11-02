"""单次历史检查内复用相同计算；原指标/策略代码及浮点运算顺序不变。"""
import numpy as np

from heart_v2.metrics import _matching_vectors, _validate_max_lag
from heart_v3a.runtime_pl_chain import RuntimePlMainChain
from . import numpy_compat as reference


class _WindowMetrics:
    """只由一次assess_history持有；输入指纹含步幅，不跨窗口缓存。"""

    def __init__(self):
        self.powers = {}
        self.correlations = {}
        self.centered = {}

    @staticmethod
    def _key(values):
        return values.shape, values.strides, values.tobytes()

    def power(self, signal):
        signal = np.asarray(signal, float)
        key = self._key(signal)
        if key not in self.powers:
            self.powers[key] = reference.band_power(signal)
        return self.powers[key]

    def _center(self, values, key, start, stop):
        part_key = key, start, stop
        if part_key not in self.centered:
            part = values[start:stop]
            centered = part - part.mean()
            # 保留原np.linalg.norm，不改变归约顺序或引入近似。
            self.centered[part_key] = centered, np.linalg.norm(centered)
        return self.centered[part_key]

    def correlation(self, output, reference_signal, max_lag):
        max_lag = _validate_max_lag(max_lag)
        output, reference_signal = _matching_vectors(output, reference_signal)
        if not (np.isfinite(output).all() and np.isfinite(reference_signal).all()):
            raise ValueError("correlation inputs must contain only finite values")
        output_key, reference_key = self._key(output), self._key(reference_signal)
        key = output_key, reference_key, max_lag
        if key not in self.correlations:
            scores = []
            n = len(output)
            for lag in range(-max_lag, max_lag + 1):
                if abs(lag) > n-2:
                    continue
                y_start, y_stop = (0, n+lag) if lag < 0 else (lag, n)
                x_start, x_stop = (-lag, n) if lag < 0 else (0, n-lag)
                y, y_norm = self._center(output, output_key, y_start, y_stop)
                x, x_norm = self._center(reference_signal, reference_key, x_start, x_stop)
                denominator = y_norm * x_norm
                scores.append(0.0 if denominator == 0 else abs(float(y @ x / denominator)))
            self.correlations[key] = max(scores, default=0.0)
        return self.correlations[key]


def assess_history(raw, candidate, magnitude, axes, actual):
    window = _WindowMetrics()
    metric = reference._bind(reference.aligned_metrics,
        max_abs_correlation=window.correlation, band_power=window.power)
    assess = reference._bind(reference.assess_history, aligned_metrics=metric)
    return assess(raw, candidate, magnitude, axes, actual)


class FastJointBenefitSelector(reference.CompatibleJointBenefitSelector):
    step = reference._bind(reference.CompatibleJointBenefitSelector.step, assess_history=assess_history)


# 控制变化也必须创建同一种选择器；不修改只读原runtime step。
runtime_step = reference._bind(RuntimePlMainChain.step, JointBenefitSelector=FastJointBenefitSelector)
