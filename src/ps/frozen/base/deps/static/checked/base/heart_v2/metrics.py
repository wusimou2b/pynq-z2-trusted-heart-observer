from dataclasses import dataclass
import math

import numpy as np
from scipy.signal import welch


PULSE_BAND_LOW_HZ = 0.7
PULSE_BAND_HIGH_HZ = 3.0


@dataclass(frozen=True)
class BranchMetrics:
    motion_leakage: float
    raw_motion_leakage: float
    motion_leakage_reduction_db: float
    output_rms_ratio: float
    pulse_band_power_ratio: float
    finite: bool


def _invalid_metrics():
    return BranchMetrics(np.nan, np.nan, np.nan, np.nan, np.nan, False)


def _validate_max_lag(max_lag):
    if (
        isinstance(max_lag, (bool, np.bool_))
        or not isinstance(max_lag, (int, np.integer))
        or max_lag < 0
    ):
        raise ValueError("max_lag must be a non-negative integer")
    return int(max_lag)


def _matching_vectors(*signals):
    arrays = tuple(np.asarray(signal, dtype=float) for signal in signals)
    if any(array.ndim != 1 for array in arrays):
        raise ValueError("metric inputs must be one-dimensional")
    if len({array.size for array in arrays}) != 1:
        raise ValueError("metric inputs must have equal lengths")
    return arrays


def max_abs_correlation(output, reference, max_lag):
    """计算有效延迟范围内的最大绝对相关系数。

    每个延迟至少需要两个重叠样本；空输入返回零。
    维度不匹配、非有限值和非法延迟配置均抛出异常。
    """
    max_lag = _validate_max_lag(max_lag)
    output, reference = _matching_vectors(output, reference)
    if not (np.isfinite(output).all() and np.isfinite(reference).all()):
        raise ValueError("correlation inputs must contain only finite values")
    scores = []
    for lag in range(-max_lag, max_lag + 1):
        if lag < 0:
            y, x = output[:lag], reference[-lag:]
        elif lag > 0:
            y, x = output[lag:], reference[:-lag]
        else:
            y, x = output, reference
        if y.size < 2:
            continue
        y, x = y - y.mean(), x - x.mean()
        denominator = np.linalg.norm(y) * np.linalg.norm(x)
        scores.append(0.0 if denominator == 0 else abs(float(y @ x / denominator)))
    return max(scores, default=0.0)


def branch_metrics(output, raw, reference, sample_rate_hz, max_lag):
    """计算一个评价窗口的分支指标。

    输入必须为等长一维数组，且至少覆盖 0.7 Hz 下的一个周期。
    窗口过短或包含非有限值时返回全 NaN 的无效记录；
    维度、采样率或延迟配置非法时抛出 ValueError。
    """
    if isinstance(sample_rate_hz, (bool, np.bool_)) or not np.isscalar(
        sample_rate_hz
    ):
        raise ValueError("sample_rate_hz must be finite and positive")
    try:
        sample_rate_hz = float(sample_rate_hz)
    except (TypeError, ValueError):
        raise ValueError("sample_rate_hz must be finite and positive") from None
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise ValueError("sample_rate_hz must be finite and positive")
    max_lag = _validate_max_lag(max_lag)
    output, raw, reference = _matching_vectors(output, raw, reference)
    finite = bool(
        np.isfinite(output).all()
        and np.isfinite(raw).all()
        and np.isfinite(reference).all()
    )
    if not finite:
        return _invalid_metrics()
    minimum_samples = math.ceil(sample_rate_hz / PULSE_BAND_LOW_HZ)
    if output.size < minimum_samples:
        return _invalid_metrics()
    leakage = max_abs_correlation(output, reference, max_lag)
    raw_leakage = max_abs_correlation(raw, reference, max_lag)
    reduction = 10.0 * np.log10(
        (raw_leakage**2 + 1e-12) / (leakage**2 + 1e-12)
    )
    output_rms_ratio = np.sqrt(np.mean(output**2)) / max(
        np.sqrt(np.mean(raw**2)), 1e-12
    )

    def pulse_power(signal):
        frequencies, density = welch(
            signal, fs=sample_rate_hz, nperseg=min(256, len(signal))
        )
        selected = (frequencies >= PULSE_BAND_LOW_HZ) & (
            frequencies <= PULSE_BAND_HIGH_HZ
        )
        return float(np.trapezoid(density[selected], frequencies[selected]))

    pulse_ratio = pulse_power(output) / max(pulse_power(raw), 1e-12)
    values = (leakage, raw_leakage, reduction, output_rms_ratio, pulse_ratio)
    if not np.isfinite(values).all():
        return _invalid_metrics()
    return BranchMetrics(
        leakage,
        raw_leakage,
        reduction,
        output_rms_ratio,
        pulse_ratio,
        True,
    )

