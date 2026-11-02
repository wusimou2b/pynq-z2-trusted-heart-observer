"""Causal sub-sample peak timing for the independent 25 Hz branch only."""
import math
from statistics import median

from heart_v2.heartrate import HeartRateState
from heart_v3a.live.single_sample import ScalarSosHeartRateDetector

PEAK_VERSION = 'raw50_process25_fractional_peaks_v2'


def peak_offset(left,center,right):
    """Vertex of a local concave three-point parabola, in sample units.

    The right neighbour has arrived already. No extrapolation beyond its
    half-sample neighbourhood and no fabricated peak on flat data.
    """
    values = tuple(float(v) for v in (left,center,right))
    if not all(math.isfinite(v) for v in values):
        raise ValueError('峰邻域必须为有限数')
    left,center,right = values
    if not left < center or right > center:
        raise ValueError('必须是已确认的局部极大值')
    scale = max(abs(v) for v in values)
    left,center,right = (v/scale for v in values)
    dl,dr = left-center,right-center
    denominator = dl+dr
    if denominator >= 0:
        raise ValueError('峰曲率不可解析')
    return max(-.5,min(.5,.5*(dl-dr)/denominator))


class FractionalPeakDetector(ScalarSosHeartRateDetector):
    def __init__(self,sample_rate_hz,**parameters):
        if sample_rate_hz != 25:
            raise ValueError('精细峰时刻候选仅用于25Hz')
        super().__init__(sample_rate_hz,**parameters)
        self.minimum_interval = 60*self.sample_rate_hz/self.max_bpm
        self.maximum_interval = 60*self.sample_rate_hz/self.min_bpm

    def reset(self):
        super().reset()
        self.last_peak_position = None
        self._interval_key = None
        self._bpm = None

    @staticmethod
    def _finite(value):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError('判峰输入必须为有限数')
        return value

    def step(self,value,trusted_allowed):
        current = self._finite(value)
        # Exact same sections/arithmetic order as the frozen scalar SOS.
        for index,(b0,b1,b2,_a0,a1,a2) in enumerate(self._sections):
            incoming = current
            current = b0*incoming+float(self.zi[index,0])
            self.zi[index,0] = b1*incoming-a1*current+float(self.zi[index,1])
            self.zi[index,1] = b2*incoming-a2*current
        return self.step_filtered(current,trusted_allowed)

    def step_filtered(self,current,trusted_allowed):
        """Peak-only path for an already filtered selected branch.

        reset() clears ALL peak/IBI history. A warm waveform is not a warm
        heart-rate estimate; the caller still requires two fresh intervals.
        """
        current = self._finite(current)
        peak = False
        if not trusted_allowed:
            self.last_peak_index = self.last_peak_position = None
            self.ibis.clear()
        else:
            self.envelope += self.threshold_alpha*(abs(current)-self.envelope)
            local_maximum = (self.previous_previous_trusted and self.previous_trusted
                             and self.previous > self.previous_previous and self.previous >= current)
            if local_maximum and self.previous > self.threshold_scale*self.envelope:
                index = self.sample_index-1
                position = index+peak_offset(self.previous_previous,self.previous,current)
                interval = None if self.last_peak_position is None else position-self.last_peak_position
                if interval is None or interval >= self.minimum_interval:
                    peak = True
                    self.accepted_peak_count += 1
                    if interval is not None and interval <= self.maximum_interval:
                        self.ibis.append(interval)
                    elif interval is not None:
                        self.ibis.clear()
                    self.last_peak_index,self.last_peak_position = index,position
        key = tuple(self.ibis)
        if key != self._interval_key:
            self._interval_key = key
            self._bpm = 60*self.sample_rate_hz/median(key) if key else None
        self.previous_previous,self.previous = self.previous,current
        self.previous_previous_trusted = bool(trusted_allowed and self.previous_trusted)
        self.previous_trusted = bool(trusted_allowed)
        self.sample_index += 1
        return HeartRateState(current,peak,self._bpm if trusted_allowed else None,
                              bool(trusted_allowed and self._bpm is not None))
