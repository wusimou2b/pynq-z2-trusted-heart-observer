"""仅 live 使用的固定 SOS 单点执行；系数及判峰契约沿用只读 V2。"""
import numpy as np

from heart_v2.heartrate import CausalHeartRateDetector, HeartRateState


class ScalarSosHeartRateDetector(CausalHeartRateDetector):
    """同一双精度 DF-II 转置递推，避免每拍通用数组布局／接口检查。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 原 butter 仍负责设计固定归一化系数；各实例 zi 仍由原 reset 清零。
        self._sections = tuple(tuple(float(value) for value in row) for row in self.sos)

    def step(self, value, trusted_allowed):
        current = float(value)
        for index, (b0, b1, b2, _a0, a1, a2) in enumerate(self._sections):
            incoming = current
            current = b0 * incoming + float(self.zi[index, 0])
            self.zi[index, 0] = b1 * incoming - a1 * current + float(self.zi[index, 1])
            self.zi[index, 1] = b2 * incoming - a2 * current

        # 以下判峰与 V2 的 step 完全同序；不可信样本也必须先更新滤波状态。
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
