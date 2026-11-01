"""供各算法分支共用的因果心率检测器。

峰值判定延迟一个样本；只有下一笔滤波样本到来后，才能确认局部极大值。
"""

from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfilt


@dataclass(frozen=True)
class HeartRateState:
    filtered: float
    peak: bool
    bpm: float | None
    trusted: bool


class CausalHeartRateDetector:
    """各分支共用的因果带通、峰值和心率检测器。"""

    def __init__(
        self,
        sample_rate_hz,
        min_bpm,
        max_bpm,
        threshold_alpha,
        threshold_scale,
        ibi_history,
    ):
        self.sample_rate_hz = float(sample_rate_hz)
        self.min_bpm = float(min_bpm)
        self.max_bpm = float(max_bpm)
        self.threshold_alpha = float(threshold_alpha)
        self.threshold_scale = float(threshold_scale)
        self.ibi_history_size = int(ibi_history)
        self.sos = butter(
            2,
            [0.7, 3.0],
            btype="bandpass",
            fs=self.sample_rate_hz,
            output="sos",
        )
        self.reset()

    def reset(self):
        self.zi = np.zeros((len(self.sos), 2), dtype=float)
        self.previous_previous = 0.0
        self.previous = 0.0
        self.previous_previous_trusted = False
        self.previous_trusted = False
        self.envelope = 0.0
        self.sample_index = 0
        self.last_peak_index = None
        self.ibis = deque(maxlen=self.ibi_history_size)
        self.accepted_peak_count = 0

    def step(self, value, trusted_allowed):
        filtered_array, self.zi = sosfilt(self.sos, [float(value)], zi=self.zi)
        current = float(filtered_array[0])
        if not trusted_allowed:
            self.previous_previous = self.previous
            self.previous = current
            self.previous_previous_trusted = False
            self.previous_trusted = False
            self.sample_index += 1
            self.last_peak_index = None
            self.ibis.clear()
            return HeartRateState(current, False, None, False)

        self.envelope += self.threshold_alpha * (abs(current) - self.envelope)
        candidate_index = self.sample_index - 1
        trustworthy_neighborhood = (
            self.previous_previous_trusted and self.previous_trusted
        )
        local_maximum = (
            trustworthy_neighborhood
            and self.previous > self.previous_previous
            and self.previous >= current
        )
        above_threshold = self.previous > self.threshold_scale * self.envelope
        min_interval = int(np.floor(60.0 * self.sample_rate_hz / self.max_bpm))
        max_interval = int(np.ceil(60.0 * self.sample_rate_hz / self.min_bpm))
        peak = False
        if local_maximum and above_threshold:
            interval = (
                None
                if self.last_peak_index is None
                else candidate_index - self.last_peak_index
            )
            if interval is None or interval >= min_interval:
                peak = True
                self.accepted_peak_count += 1
                if interval is not None and interval <= max_interval:
                    self.ibis.append(interval)
                elif interval is not None:
                    self.ibis.clear()
                self.last_peak_index = candidate_index

        bpm = (
            None
            if not self.ibis
            else 60.0 * self.sample_rate_hz / float(np.median(self.ibis))
        )
        self.previous_previous = self.previous
        self.previous = current
        self.previous_previous_trusted = self.previous_trusted
        self.previous_trusted = True
        self.sample_index += 1
        return HeartRateState(current, peak, bpm, bpm is not None)
