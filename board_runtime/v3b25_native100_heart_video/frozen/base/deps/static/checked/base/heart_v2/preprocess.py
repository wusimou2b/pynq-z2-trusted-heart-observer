from dataclasses import dataclass

import numpy as np


class CausalDcBlocker:
    def __init__(self, alpha):
        self.alpha = float(alpha)
        self.reset()

    def reset(self, initial_input=0.0):
        """初始化输入基线并清零输出；传入首个有效值可避免启动冲击。"""
        self.previous_input = float(initial_input)
        self.previous_output = 0.0

    def step(self, value):
        value = float(value)
        output = value - self.previous_input + self.alpha * self.previous_output
        self.previous_input = value
        self.previous_output = output
        return output


@dataclass(frozen=True)
class PreprocessedSignals:
    ppg: np.ndarray
    reference: np.ndarray


def preprocess_capture(
    ir_raw,
    ax_g,
    ay_g,
    az_g,
    ppg_alpha,
    reference_alpha,
    ppg_scale,
    reference_scale,
):
    ax_g, ay_g, az_g = (np.asarray(values, dtype=float) for values in (ax_g, ay_g, az_g))
    magnitude = np.sqrt(ax_g * ax_g + ay_g * ay_g + az_g * az_g)
    ppg_values = np.asarray(ir_raw, dtype=float)
    reference_values = np.asarray(magnitude, dtype=float)
    if ppg_alpha != 0.0:
        ppg_filter = CausalDcBlocker(ppg_alpha)
        # 每个连续有效区间只用当前首样本建基线，不读取未来样本。
        if ppg_values.size:
            ppg_filter.reset(initial_input=ppg_values[0])
        ppg_values = np.array([ppg_filter.step(x) for x in ppg_values])
    if reference_alpha != 0.0:
        ref_filter = CausalDcBlocker(reference_alpha)
        if reference_values.size:
            ref_filter.reset(initial_input=reference_values[0])
        reference_values = np.array([ref_filter.step(x) for x in reference_values])
    ppg = ppg_values / ppg_scale
    reference = reference_values / reference_scale
    return PreprocessedSignals(ppg=ppg, reference=reference)


def phase_mask(time_s, phases, label, guard_seconds):
    time_s = np.asarray(time_s, dtype=float)
    phases = np.asarray(phases, dtype=str)
    mask = np.zeros(len(time_s), dtype=bool)
    if not len(time_s):
        return mask
    boundaries = np.flatnonzero(np.r_[True, phases[1:] != phases[:-1], True])
    median_dt = np.median(np.diff(time_s)) if len(time_s) > 1 else 0.0
    for start, stop in zip(boundaries[:-1], boundaries[1:]):
        if phases[start] != label:
            continue
        run_start = time_s[start]
        run_stop = time_s[stop] if stop < len(time_s) else time_s[-1] + median_dt
        mask[start:stop] = (
            (time_s[start:stop] >= run_start + guard_seconds)
            & (time_s[start:stop] < run_stop - guard_seconds)
        )
    return mask
