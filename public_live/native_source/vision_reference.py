"""Integer golden reference for a future PL vision kernel, not a live pipeline.

Input uses OpenCV BGR byte order, not YUYV bytes. The Q8 luma definition is
deliberately explicit rather than claiming bit equality with cv2.cvtColor.
"""
from dataclasses import dataclass
from numbers import Integral

import numpy as np


INPUT_SHAPE = (480, 640, 3)
OUTPUT_SHAPE = (240, 320)


def _integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise TypeError(name + " must be an integer, not a boolean")
    return int(value)


def _uint8_image(image):
    if not isinstance(image, np.ndarray) or image.dtype != np.dtype("uint8"):
        raise TypeError("expected a uint8 NumPy array")


@dataclass(frozen=True)
class Roi:
    """Fixed half-open rectangle in the 320x240 output, not a detected subject."""
    x: int = 80
    y: int = 60
    width: int = 160
    height: int = 120

    def __post_init__(self):
        for name in ("x", "y", "width", "height"):
            object.__setattr__(self, name, _integer(getattr(self, name), name))
        if (self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0
                or self.x + self.width > OUTPUT_SHAPE[1]
                or self.y + self.height > OUTPUT_SHAPE[0]):
            raise ValueError("ROI must be a nonempty rectangle inside 320x240")


def bgr_to_luma8(bgr):
    """Round each Q8 weighted BGR pixel before any spatial averaging."""
    _uint8_image(bgr)
    if bgr.ndim != 3 or bgr.shape[2] != 3 or min(bgr.shape[:2]) <= 0:
        raise ValueError("expected nonempty HxWx3 BGR")
    wide = bgr.astype(np.uint32)
    return ((77 * wide[..., 2] + 150 * wide[..., 1]
             + 29 * wide[..., 0] + 128) >> 8).astype(np.uint8)


def downsample2x2_round(luma):
    """Non-overlapping 2x2 box mean, half rounded up, uint8 result."""
    _uint8_image(luma)
    if luma.ndim != 2 or min(luma.shape) <= 0 or any(size % 2 for size in luma.shape):
        raise ValueError("expected nonempty even-height, even-width luma image")
    wide = luma.astype(np.uint16)
    return ((wide[0::2, 0::2] + wide[0::2, 1::2]
             + wide[1::2, 0::2] + wide[1::2, 1::2] + 2) >> 2).astype(np.uint8)


def gray_downsample_bgr(bgr):
    """Fixed camera geometry: 640x480 BGR -> 320x240 integer luma."""
    _uint8_image(bgr)
    if bgr.shape != INPUT_SHAPE:
        raise ValueError("expected 480x640x3 BGR camera frame")
    return downsample2x2_round(bgr_to_luma8(bgr))


@dataclass(frozen=True)
class VisionStats:
    epoch: int
    sequence: int
    timestamp_ns: int
    previous_sequence: int | None
    previous_timestamp_ns: int | None
    pair_elapsed_ns: int | None
    missed_frames: int
    roi: Roi
    pixel_count: int
    luma_sum: int
    luma_min: int
    luma_max: int
    difference_valid: bool
    reason: str
    diff_sum: int | None
    diff_max: int | None


class VisionReference:
    """Retain one owned ROI, never a camera buffer or unbounded frame history.

    Timestamps are caller-supplied read-completion monotonic times, not exposure
    times. The pair-gap limit is not a display freshness or medical threshold.
    This object is for a single sequential consumer, not concurrent mutation.
    """

    def __init__(self, roi=None, maximum_pair_gap_ns=250_000_000):
        self._roi = Roi() if roi is None else roi
        if not isinstance(self._roi, Roi):
            raise TypeError("roi must be a validated Roi")
        self._maximum_pair_gap_ns = _integer(maximum_pair_gap_ns, "maximum_pair_gap_ns")
        if self._maximum_pair_gap_ns <= 0:
            raise ValueError("maximum_pair_gap_ns must be positive")
        self._epoch = -1
        self.reset()

    @property
    def roi(self):
        return self._roi

    @property
    def maximum_pair_gap_ns(self):
        return self._maximum_pair_gap_ns

    def reset(self):
        """Explicit new stream epoch, including re-prime after disconnection."""
        self._epoch += 1
        self._previous_roi = None
        self._previous_sequence = None
        self._previous_timestamp_ns = None

    def process(self, bgr, *, sequence, timestamp_ns):
        sequence = _integer(sequence, "sequence")
        timestamp_ns = _integer(timestamp_ns, "timestamp_ns")
        if sequence < 0 or timestamp_ns < 0:
            raise ValueError("sequence and timestamp_ns must be nonnegative")
        if self._previous_sequence is not None and sequence <= self._previous_sequence:
            raise ValueError("sequence must increase strictly within an epoch")
        if self._previous_timestamp_ns is not None and timestamp_ns <= self._previous_timestamp_ns:
            raise ValueError("timestamp_ns must increase strictly within an epoch")
        small = gray_downsample_bgr(bgr)
        roi = self._roi
        current = small[roi.y:roi.y + roi.height, roi.x:roi.x + roi.width].copy()
        elapsed = (None if self._previous_timestamp_ns is None
                   else timestamp_ns - self._previous_timestamp_ns)
        missed = (0 if self._previous_sequence is None
                  else sequence - self._previous_sequence - 1)
        diff_sum = diff_max = None
        if self._previous_roi is None:
            reason = "first_frame"
        elif missed:
            reason = "sequence_gap"
        elif elapsed > self._maximum_pair_gap_ns:
            reason = "timestamp_gap"
        else:
            reason = "ok"
            delta = np.abs(current.astype(np.int16) - self._previous_roi.astype(np.int16))
            diff_sum = int(delta.sum(dtype=np.uint64))
            diff_max = int(delta.max())
        result = VisionStats(
            epoch=self._epoch, sequence=sequence, timestamp_ns=timestamp_ns,
            previous_sequence=self._previous_sequence,
            previous_timestamp_ns=self._previous_timestamp_ns, pair_elapsed_ns=elapsed,
            missed_frames=missed, roi=roi, pixel_count=current.size,
            luma_sum=int(current.sum(dtype=np.uint64)), luma_min=int(current.min()),
            luma_max=int(current.max()), difference_valid=reason == "ok", reason=reason,
            diff_sum=diff_sum, diff_max=diff_max)
        # Only a completely accepted frame can become the next owned baseline.
        self._previous_roi = current
        self._previous_sequence = sequence
        self._previous_timestamp_ns = timestamp_ns
        return result
