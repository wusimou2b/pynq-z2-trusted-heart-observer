"""固定200点谱段、统一频率网格、显式补齐尾部；旧指标保持不动。"""
from dataclasses import dataclass
import numpy as np
from scipy.signal import welch
from .metrics import max_abs_correlation

VERSION = 'aligned_200_tail_v1'


@dataclass(frozen=True)
class AlignedMetrics:
    motion_leakage: float
    raw_motion_leakage: float
    motion_leakage_reduction_db: float
    output_rms_ratio: float
    pulse_band_power_ratio: float
    finite: bool
    metric_version: str
    nperseg: int
    segment_starts: tuple
    segment_count: int
    coverage_start: int
    coverage_stop: int


def segment_starts(n):
    if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 0:
        raise ValueError('sample count must be a nonnegative integer')
    if n < 200:
        return ()
    starts = list(range(0, n-199, 100))
    if starts[-1] != n-200:
        starts.append(n-200)
    return tuple(starts)


def band_power(signal):
    signal = np.asarray(signal, float)
    if signal.ndim != 1:
        raise ValueError('power input must be one-dimensional')
    starts = segment_starts(len(signal))
    if not starts or not np.isfinite(signal).all():
        return float('nan')
    parts = []
    for start in starts:
        f, p = welch(signal[start:start+200], fs=50, window='hann', nperseg=200,
                     noverlap=0, nfft=200, detrend='constant', scaling='density')
        band = (f >= .7) & (f <= 3.)
        parts.append(float(np.trapezoid(p[band], f[band])))
    return float(np.mean(parts))


def aligned_metrics(output, raw, reference):
    output, raw, reference = [np.asarray(v, float) for v in (output, raw, reference)]
    if any(v.ndim != 1 for v in (output,raw,reference)) or len({len(v) for v in (output,raw,reference)}) != 1:
        raise ValueError('metric vectors must have matching one-dimensional shapes')
    starts = segment_starts(len(output))
    metadata = dict(metric_version=VERSION, nperseg=200, segment_starts=starts,
                    segment_count=len(starts), coverage_start=0 if starts else -1,
                    coverage_stop=len(output) if starts else -1)
    invalid = lambda: AlignedMetrics(*([np.nan]*5), finite=False, **metadata)
    if not starts or not all(np.isfinite(v).all() for v in (output,raw,reference)):
        return invalid()
    with np.errstate(over='ignore', invalid='ignore', divide='ignore'):
        leakage = max_abs_correlation(output,reference,10)
        original = max_abs_correlation(raw,reference,10)
        improvement = 10*np.log10((original**2+1e-12)/(leakage**2+1e-12))
        rms = np.sqrt(np.mean(output**2))/max(np.sqrt(np.mean(raw**2)),1e-12)
        power = band_power(output)/max(band_power(raw),1e-12)
    values = (leakage, original, improvement, rms, power)
    if not np.isfinite(values).all():
        return invalid()
    return AlignedMetrics(*map(float,values), finite=True, **metadata)
