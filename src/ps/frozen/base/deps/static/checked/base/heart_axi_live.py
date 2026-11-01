"""Continuous PYNQ MAX30102/MPU6050 monitor with AXI FIFO verification.

Copy this file beside ``heart_axi_iic.bit`` and ``heart_axi_iic.hwh`` on the
PYNQ board.  In a notebook run::

    from heart_axi_live import start_monitor
    monitor = start_monitor("./heart_axi_iic.bit")

The hardware is accessed by one worker thread.  The notebook event loop only
updates Bokeh data sources and handles the Stop button.
"""

import asyncio
import csv
import html
import math
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks


NOTEBOOK_PLOT_WIDTH = 1000
_ACTIVE_MONITOR = None
_ACTIVE_MONITOR_LOCK = threading.RLock()


def notebook_figure_kwargs(height):
    """Return a stable classic-Notebook figure size.

    Responsive Bokeh sizing can observe a near-zero parent width while a classic
    Notebook output cell is still being attached.  A fixed width avoids the
    permanently collapsed plots that otherwise result from that race.
    """
    height = int(height)
    if height <= 0:
        raise ValueError("height must be positive")
    return {
        "height": height,
        "width": NOTEBOOK_PLOT_WIDTH,
        "sizing_mode": "fixed",
    }


def notebook_container_kwargs():
    """Keep notebook containers wide while allowing their height to fit content."""
    return {"width": NOTEBOOK_PLOT_WIDTH}


def fifo_available(write_pointer, read_pointer, overflow):
    """Return the MAX30102 FIFO sample count, including the full-FIFO case."""
    write_pointer &= 0x1F
    read_pointer &= 0x1F
    if write_pointer == read_pointer:
        return 32 if overflow else 0
    return (write_pointer - read_pointer) & 0x1F


MAX30102_SAMPLE_AVERAGE_BITS = {
    1: 0b000,
    2: 0b001,
    4: 0b010,
    8: 0b011,
    16: 0b100,
    32: 0b101,
}


def max30102_fifo_config(sample_average=4, almost_full=15, rollover=False):
    """Encode MAX30102 FIFO_CONFIG without hiding the decimation setting."""
    try:
        average_bits = MAX30102_SAMPLE_AVERAGE_BITS[int(sample_average)]
    except (KeyError, TypeError, ValueError):
        raise ValueError("sample_average must be one of 1, 2, 4, 8, 16, 32")
    almost_full = int(almost_full)
    if not 0 <= almost_full <= 15:
        raise ValueError("almost_full must be between 0 and 15")
    return (average_bits << 5) | (int(bool(rollover)) << 4) | almost_full


def pack_sample(sequence, timestamp_us, ir, ax_raw, ay_raw, az_raw):
    """Encode one application sample as the six-word PL loopback packet."""
    return [
        sequence & 0xFFFFFFFF,
        timestamp_us & 0xFFFFFFFF,
        ir & 0xFFFFFFFF,
        ax_raw & 0xFFFF,
        ay_raw & 0xFFFF,
        az_raw & 0xFFFF,
    ]


def signed16(value):
    """Decode the low 16 bits of *value* as a signed integer."""
    value &= 0xFFFF
    return value - 0x10000 if value & 0x8000 else value


@dataclass(frozen=True)
class HeartRateResult:
    """Signal-processing result aligned to the input window."""

    smoothed: np.ndarray
    filtered: np.ndarray
    peak_indices: np.ndarray
    bpm: float
    trusted: bool


CONTACT_BASELINE_SECONDS = 1.0
CONTACT_AMPLITUDE_SECONDS = 3.0
CONTACT_COMPARE_SECONDS = 0.8
CONTACT_PRE_SECONDS = 1.0
CONTACT_RECOVERY_SECONDS = 2.0
CONTACT_MIN_IR = 10000.0
CONTACT_MAX_IR = 250000.0
CONTACT_MIN_AMPLITUDE = 250.0
CONTACT_MIN_STEP = 2500.0
CONTACT_STEP_AMPLITUDE_FACTOR = 2.5


@dataclass(frozen=True)
class ContactQualityResult:
    """Contact diagnostics aligned sample-for-sample with an IR window."""

    baseline: np.ndarray
    pulse_amplitude: np.ndarray
    quality_score: np.ndarray
    contact_ok: np.ndarray
    reason: np.ndarray


def _expand_events(events, before, after):
    events = np.asarray(events, dtype=bool)
    expanded = np.zeros(events.size, dtype=bool)
    for index in np.flatnonzero(events):
        start = max(0, index - int(before))
        stop = min(events.size, index + int(after) + 1)
        expanded[start:stop] = True
    return expanded


def _trailing_windows(values, width):
    """Return an edge-padded, read-only trailing-window view."""
    values = np.ascontiguousarray(values, dtype=float)
    width = max(1, int(width))
    padded = np.pad(values, (width - 1, 0), mode="edge")
    stride = padded.strides[0]
    return np.lib.stride_tricks.as_strided(
        padded,
        shape=(values.size, width),
        strides=(stride, stride),
        writeable=False,
    )


def contact_quality(ir_values, sample_rate):
    """Detect poor finger contact and pressure-driven MAX30102 baseline shifts."""
    ir_values = np.asarray(ir_values, dtype=float)
    sample_rate = float(sample_rate)
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive finite value")
    count = ir_values.size
    if count == 0:
        empty = np.zeros(0, dtype=float)
        return ContactQualityResult(
            empty, empty, empty, np.zeros(0, dtype=bool), np.zeros(0, dtype=object)
        )

    baseline_samples = max(1, int(round(CONTACT_BASELINE_SECONDS * sample_rate)))
    amplitude_samples = max(1, int(round(CONTACT_AMPLITUDE_SECONDS * sample_rate)))
    compare_samples = max(1, int(round(CONTACT_COMPARE_SECONDS * sample_rate)))
    pre_samples = max(0, int(round(CONTACT_PRE_SECONDS * sample_rate)))
    recovery_samples = max(0, int(round(CONTACT_RECOVERY_SECONDS * sample_rate)))

    baseline = np.median(_trailing_windows(ir_values, baseline_samples), axis=1)
    detrended = ir_values - baseline
    amplitude_windows = _trailing_windows(detrended, amplitude_samples)
    pulse_amplitude = 0.5 * (
        np.percentile(amplitude_windows, 95, axis=1)
        - np.percentile(amplitude_windows, 5, axis=1)
    )

    baseline_shift = np.zeros(count, dtype=float)
    if count > compare_samples:
        baseline_shift[compare_samples:] = np.abs(
            ir_values[compare_samples:] - baseline[:-compare_samples]
        )
    step_threshold = np.maximum(
        CONTACT_MIN_STEP,
        CONTACT_STEP_AMPLITUDE_FACTOR * pulse_amplitude,
    )
    step_event = baseline_shift > step_threshold
    step_event[:compare_samples] = False

    too_low = ir_values < CONTACT_MIN_IR
    saturated = ir_values > CONTACT_MAX_IR
    weak = np.zeros(count, dtype=bool)
    warmup_index = amplitude_samples - 1
    if warmup_index < count:
        weak[warmup_index:] = pulse_amplitude[warmup_index:] < CONTACT_MIN_AMPLITUDE

    step_bad = _expand_events(step_event, pre_samples, recovery_samples)
    low_bad = _expand_events(too_low, 0, recovery_samples)
    saturated_bad = _expand_events(saturated, 0, recovery_samples)
    weak_bad = _expand_events(weak, 0, recovery_samples)

    reason = np.full(count, "ok", dtype=object)
    reason[weak_bad] = "pulse_too_weak"
    reason[step_bad] = "baseline_jump"
    reason[saturated_bad] = "ir_saturated"
    reason[low_bad] = "ir_too_low"
    contact_ok = reason == "ok"

    score = np.full(count, 100.0, dtype=float)
    score[weak_bad] = np.minimum(score[weak_bad], 25.0)
    for index in np.flatnonzero(step_event):
        severity = baseline_shift[index] / max(step_threshold[index], 1.0)
        event_score = float(np.clip(100.0 - 50.0 * severity, 5.0, 49.0))
        start = max(0, index - pre_samples)
        stop = min(count, index + recovery_samples + 1)
        score[start:stop] = np.minimum(score[start:stop], event_score)
    score[low_bad | saturated_bad] = 0.0
    return ContactQualityResult(
        baseline=baseline,
        pulse_amplitude=pulse_amplitude,
        quality_score=np.clip(score, 0.0, 100.0),
        contact_ok=contact_ok,
        reason=reason,
    )


def _moving_average(values, width=4):
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return values.copy()
    width = max(1, min(int(width), values.size))
    kernel = np.ones(width, dtype=float) / width
    padded = np.pad(values, (width - 1, 0), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def expanded_motion_mask(acceleration_magnitude, threshold=0.08):
    """Mark abrupt acceleration changes and expand them by two samples."""
    magnitude = np.asarray(acceleration_magnitude, dtype=float)
    if magnitude.size == 0:
        return np.zeros(0, dtype=bool)
    abrupt = np.zeros(magnitude.size, dtype=bool)
    if magnitude.size > 1:
        abrupt[1:] = np.abs(np.diff(magnitude)) > float(threshold)
    kernel = np.ones(5, dtype=np.uint8)
    expanded = np.convolve(abrupt.astype(np.uint8), kernel, mode="full")
    radius = kernel.size // 2
    return expanded[radius:radius + magnitude.size] > 0


def estimate_bpm(times, ir_values, motion_mask, sample_rate):
    """Estimate motion-rejected BPM from one bounded rolling window."""
    times = np.asarray(times, dtype=float)
    ir_values = np.asarray(ir_values, dtype=float)
    motion_mask = np.asarray(motion_mask, dtype=bool)
    if not (times.size == ir_values.size == motion_mask.size):
        raise ValueError("times, ir_values and motion_mask must have equal lengths")

    smoothed = _moving_average(ir_values, 4)
    empty_peaks = np.zeros(0, dtype=int)
    invalid = HeartRateResult(smoothed, smoothed - np.mean(smoothed) if smoothed.size else smoothed,
                              empty_peaks, float("nan"), False)
    sample_rate = float(sample_rate)
    if times.size < 16 or not np.isfinite(sample_rate) or sample_rate <= 4.0:
        return invalid

    try:
        nyquist = sample_rate / 2.0
        low = 0.5 / nyquist
        high = 2.0 / nyquist
        if not 0.0 < low < high < 1.0:
            return invalid
        b_coeff, a_coeff = butter(2, [low, high], btype="bandpass")
        filtered = filtfilt(b_coeff, a_coeff, smoothed)
    except (ValueError, FloatingPointError):
        return invalid

    prominence = max(50.0, 0.35 * float(np.std(filtered)))
    distance = max(1, int(sample_rate * 0.4))
    candidates, _ = find_peaks(filtered, distance=distance, prominence=prominence)
    clean_peaks = candidates[~motion_mask[candidates]]
    if clean_peaks.size < 3:
        return HeartRateResult(smoothed, filtered, clean_peaks, float("nan"), False)

    intervals = np.diff(times[clean_peaks])
    valid_intervals = intervals[(intervals >= 0.4) & (intervals <= 1.5)]
    if valid_intervals.size < 2:
        return HeartRateResult(smoothed, filtered, clean_peaks, float("nan"), False)

    bpm = 60.0 / float(np.median(valid_intervals[-5:]))
    recent_motion = bool(np.any(motion_mask[-max(1, int(sample_rate * 2.0)):]))
    trusted = bool(np.isfinite(bpm) and 40.0 <= bpm <= 150.0 and not recent_motion)
    return HeartRateResult(smoothed, filtered, clean_peaks, bpm, trusted)


@dataclass(frozen=True)
class Max30102FifoBatch:
    """All IR samples consumed by one MAX30102 FIFO burst."""

    ir_samples: tuple
    available: int
    overflow: int
    write_pointer: int
    read_pointer: int


class SensorBus:
    """CFFI-safe AXI IIC access for MAX30102 and MPU6050."""

    MAX_ADDRESS = 0x57
    MPU_ADDRESS = 0x68

    def __init__(self, iic):
        from cffi import FFI

        self.iic = iic
        self.ffi = FFI()

    def write_register(self, address, register, value):
        payload = self.ffi.new(
            "unsigned char[]", [int(register) & 0xFF, int(value) & 0xFF]
        )
        sent = self.iic.send(int(address), payload, 2, 0)
        if sent != 2:
            raise IOError(
                "I2C write failed at address 0x{:02X}, register 0x{:02X}: {} bytes".format(
                    address, register, sent
                )
            )

    def read_registers(self, address, register, length):
        if length <= 0:
            return b""
        register_buffer = self.ffi.new("unsigned char[]", [int(register) & 0xFF])
        sent = self.iic.send(int(address), register_buffer, 1, 1)
        if sent != 1:
            raise IOError(
                "I2C register select failed at address 0x{:02X}: {} bytes".format(
                    address, sent
                )
            )
        receive_buffer = self.ffi.new("unsigned char[]", int(length))
        received = self.iic.receive(int(address), receive_buffer, int(length), 0)
        if received != length:
            raise IOError(
                "I2C read failed at address 0x{:02X}, register 0x{:02X}: "
                "expected {}, got {} bytes".format(address, register, length, received)
            )
        return bytes(self.ffi.buffer(receive_buffer, length))

    def read_register(self, address, register):
        return self.read_registers(address, register, 1)[0]

    def verify_identities(self):
        max_id = self.read_register(self.MAX_ADDRESS, 0xFF)
        mpu_id = self.read_register(self.MPU_ADDRESS, 0x75)
        if max_id != 0x15:
            raise RuntimeError(
                "MAX30102 identity mismatch: expected 0x15, got 0x{:02X}".format(max_id)
            )
        if mpu_id != 0x68:
            raise RuntimeError(
                "MPU6050 identity mismatch: expected 0x68, got 0x{:02X}".format(mpu_id)
            )
        return max_id, mpu_id

    def clear_max30102_fifo(self):
        """Put all MAX30102 FIFO pointers into the same known-empty state."""
        for register in (0x04, 0x05, 0x06):
            self.write_register(self.MAX_ADDRESS, register, 0x00)

    def configure(
        self,
        fifo_sample_average=4,
        mpu_sample_rate_hz=None,
        mpu_dlpf_cfg=4,
    ):
        self.write_register(self.MAX_ADDRESS, 0x09, 0x40)
        deadline = time.monotonic() + 1.0
        while self.read_register(self.MAX_ADDRESS, 0x09) & 0x40:
            if time.monotonic() >= deadline:
                raise TimeoutError("MAX30102 reset did not complete")
            time.sleep(0.01)

        self.clear_max30102_fifo()
        fifo_config = max30102_fifo_config(
            sample_average=fifo_sample_average,
            almost_full=15,
            rollover=False,
        )
        self.write_register(self.MAX_ADDRESS, 0x08, fifo_config)
        self.write_register(self.MAX_ADDRESS, 0x0A, 0x23)
        self.write_register(self.MAX_ADDRESS, 0x0C, 0x24)
        self.write_register(self.MAX_ADDRESS, 0x0D, 0x24)
        self.write_register(self.MAX_ADDRESS, 0x09, 0x03)
        self.write_register(self.MPU_ADDRESS, 0x6B, 0x00)
        if mpu_sample_rate_hz is not None:
            mpu_sample_rate_hz = float(mpu_sample_rate_hz)
            mpu_dlpf_cfg = int(mpu_dlpf_cfg)
            if not 1 <= mpu_dlpf_cfg <= 6:
                raise ValueError("mpu_dlpf_cfg must be between 1 and 6")
            if not math.isfinite(mpu_sample_rate_hz) or not 1 <= mpu_sample_rate_hz <= 1000:
                raise ValueError("mpu_sample_rate_hz must be between 1 and 1000")
            divider = int(round(1000.0 / mpu_sample_rate_hz - 1.0))
            actual_rate = 1000.0 / (divider + 1)
            if not math.isclose(actual_rate, mpu_sample_rate_hz, rel_tol=0, abs_tol=1e-9):
                raise ValueError(
                    "mpu_sample_rate_hz must divide the 1000 Hz DLPF output rate"
                )
            self.write_register(self.MPU_ADDRESS, 0x1A, mpu_dlpf_cfg)
            self.write_register(self.MPU_ADDRESS, 0x19, divider)
            self.write_register(self.MPU_ADDRESS, 0x1C, 0x00)
        time.sleep(0.1)

        configuration = {
            "fifo_config": self.read_register(self.MAX_ADDRESS, 0x08),
            "mode_config": self.read_register(self.MAX_ADDRESS, 0x09),
            "spo2_config": self.read_register(self.MAX_ADDRESS, 0x0A),
            "led1_pa": self.read_register(self.MAX_ADDRESS, 0x0C),
            "led2_pa": self.read_register(self.MAX_ADDRESS, 0x0D),
        }
        if mpu_sample_rate_hz is not None:
            configuration.update(
                {
                    "mpu_sample_rate_divider": self.read_register(
                        self.MPU_ADDRESS, 0x19
                    ),
                    "mpu_dlpf_config": self.read_register(self.MPU_ADDRESS, 0x1A),
                    "mpu_accel_config": self.read_register(self.MPU_ADDRESS, 0x1C),
                }
            )
        return configuration

    def read_fifo_ir_samples(self, timeout=0.5):
        """Read and return every IR sample currently waiting in the FIFO."""
        deadline = time.monotonic() + float(timeout)
        while True:
            pointers = self.read_registers(self.MAX_ADDRESS, 0x04, 3)
            write_pointer = pointers[0] & 0x1F
            overflow = pointers[1] & 0x1F
            read_pointer = pointers[2] & 0x1F
            available = fifo_available(write_pointer, read_pointer, overflow)
            if available:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("MAX30102 FIFO wait timed out")
            time.sleep(0.002)

        fifo_bytes = self.read_registers(self.MAX_ADDRESS, 0x07, available * 6)
        ir_samples = tuple(
            ((fifo_bytes[index + 3] & 0x03) << 16)
            | (fifo_bytes[index + 4] << 8)
            | fifo_bytes[index + 5]
            for index in range(0, len(fifo_bytes), 6)
        )
        if overflow:
            self.write_register(self.MAX_ADDRESS, 0x05, 0x00)
        return Max30102FifoBatch(
            ir_samples=ir_samples,
            available=available,
            overflow=overflow,
            write_pointer=write_pointer,
            read_pointer=read_pointer,
        )

    def read_latest_ir(self, timeout=0.5):
        """Return the newest sample while preserving the accepted V1 API."""
        batch = self.read_fifo_ir_samples(timeout=timeout)
        return (
            batch.ir_samples[-1],
            batch.available,
            batch.overflow,
            batch.write_pointer,
            batch.read_pointer,
        )

    def read_acceleration_raw(self):
        data = self.read_registers(self.MPU_ADDRESS, 0x3B, 6)
        values = []
        for offset in (0, 2, 4):
            values.append(signed16((data[offset] << 8) | data[offset + 1]))
        return tuple(values)


class AxiFifoLoopback:
    """Minimal polled driver for an AXI4-Stream FIFO MM-S loopback."""

    ISR = 0x00
    TDFR = 0x08
    TDFV = 0x0C
    TDFD = 0x10
    TLR = 0x14
    RDFR = 0x18
    RDFO = 0x1C
    RDFD = 0x20
    RLR = 0x24
    RESET_MAGIC = 0xA5

    def __init__(self, mmio):
        self.mmio = mmio

    def reset(self):
        self.mmio.write(self.TDFR, self.RESET_MAGIC)
        self.mmio.write(self.RDFR, self.RESET_MAGIC)
        self.mmio.write(self.ISR, 0xFFFFFFFF)
        deadline = time.monotonic() + 0.25
        while self.mmio.read(self.TDFV) == 0:
            if time.monotonic() >= deadline:
                raise TimeoutError("AXI FIFO reset did not restore TX vacancy")
            time.sleep(0.001)

    def round_trip(self, words, timeout=0.1):
        words = [int(word) & 0xFFFFFFFF for word in words]
        if not words:
            raise ValueError("AXI FIFO packet cannot be empty")

        deadline = time.monotonic() + float(timeout)
        while self.mmio.read(self.TDFV) < len(words):
            if time.monotonic() >= deadline:
                raise TimeoutError("AXI FIFO TX vacancy wait timed out")
            time.sleep(0.0005)

        for word in words:
            self.mmio.write(self.TDFD, word)
        self.mmio.write(self.TLR, len(words) * 4)

        deadline = time.monotonic() + float(timeout)
        while self.mmio.read(self.RDFO) == 0:
            if time.monotonic() >= deadline:
                raise TimeoutError("AXI FIFO RX packet wait timed out")
            time.sleep(0.0005)

        byte_length = self.mmio.read(self.RLR) & 0x7FFFFF
        if byte_length != len(words) * 4:
            self.reset()
            raise IOError(
                "AXI FIFO length mismatch: expected {}, got {} bytes".format(
                    len(words) * 4, byte_length
                )
            )
        received = [self.mmio.read(self.RDFD) & 0xFFFFFFFF for _ in words]
        self.mmio.write(self.ISR, 0xFFFFFFFF)
        if received != words:
            raise IOError(
                "AXI FIFO data mismatch: expected {!r}, got {!r}".format(words, received)
            )
        return received


@dataclass(frozen=True)
class Sample:
    sequence: int
    timestamp_us: int
    time_s: float
    ir_raw: float
    ir_smooth: float
    ir_filtered: float
    ax_g: float
    ay_g: float
    az_g: float
    motion: bool
    baseline_ir: float
    pulse_amplitude: float
    contact_ok: bool
    quality_score: float
    quality_reason: str
    bpm: float
    trusted: bool
    sensor_ok: bool
    fifo_ok: bool
    error: str = ""


CSV_FIELDS = tuple(Sample.__dataclass_fields__.keys())


class HeartAxiMonitor:
    """Own continuous acquisition, display state, and the output CSV."""

    def __init__(
        self,
        sensors,
        fifo,
        output_dir=".",
        sample_rate=10.0,
        window_seconds=30.0,
    ):
        self.sensors = sensors
        self.fifo = fifo
        self.sample_rate = float(sample_rate)
        self.window_seconds = float(window_seconds)
        if self.sample_rate <= 0 or self.window_seconds <= 0:
            raise ValueError("sample_rate and window_seconds must be positive")

        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        max_records = max(32, int(self.sample_rate * self.window_seconds * 1.5))
        self._records = deque(maxlen=max_records)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._finished_event = threading.Event()
        self._thread = None
        self._ui_task = None
        self._handle = None
        self._sources = {}
        self._status_div = None
        self._motion_div = None
        self._x_range = None
        self.stop_button = None

        self.state = "ready"
        self.csv_path = None
        self.total_cycles = 0
        self.valid_samples = 0
        self.sensor_errors = 0
        self.fifo_errors = 0
        self.late_cycles = 0
        self.max_overflow_events = 0
        self.last_error = ""

    def start(self):
        if self._thread and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._finished_event.clear()
        self.state = "running"
        self._thread = threading.Thread(
            target=self._worker,
            name="heart-axi-acquisition",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self, wait=True, timeout=5.0):
        """Request a stop and optionally wait until the CSV is fully closed."""
        if self.state in ("running", "ready"):
            self.state = "stopping"
        self._stop_event.set()

        thread = self._thread
        if thread is None:
            self.state = "stopped"
            self._finished_event.set()
            return True

        if wait and threading.current_thread() is not thread:
            finished = self._finished_event.wait(timeout)
            if finished:
                thread.join(timeout=0)
            return bool(finished and not thread.is_alive())
        return self._finished_event.is_set()

    def close_ui(self):
        """Retire this monitor's notebook update task before a replacement UI."""
        task = self._ui_task
        if task is not None and not task.done():
            task.cancel()
        self._ui_task = None
        if self.stop_button is not None:
            self.stop_button.disabled = True
            self.stop_button.description = "Stopped — CSV saved"

    def wait(self, timeout=None):
        return self._finished_event.wait(timeout)

    def snapshot(self):
        with self._lock:
            return list(self._records)

    def counters(self):
        with self._lock:
            return {
                "state": self.state,
                "total_cycles": self.total_cycles,
                "valid_samples": self.valid_samples,
                "sensor_errors": self.sensor_errors,
                "fifo_errors": self.fifo_errors,
                "late_cycles": self.late_cycles,
                "max_overflow_events": self.max_overflow_events,
                "last_error": self.last_error,
                "csv_path": str(self.csv_path) if self.csv_path else "",
            }

    def _processed_current(self, relative_time, ir, acceleration_g):
        records = [
            record
            for record in self.snapshot()
            if record.sensor_ok and record.fifo_ok and math.isfinite(record.ir_raw)
        ]
        cutoff = relative_time - self.window_seconds
        records = [record for record in records if record.time_s >= cutoff]

        times = np.array([record.time_s for record in records] + [relative_time])
        ir_values = np.array([record.ir_raw for record in records] + [float(ir)])
        magnitudes = np.array(
            [
                math.sqrt(record.ax_g ** 2 + record.ay_g ** 2 + record.az_g ** 2)
                for record in records
            ]
            + [math.sqrt(sum(axis * axis for axis in acceleration_g))]
        )
        motion = expanded_motion_mask(magnitudes)
        if times.size > 2:
            intervals = np.diff(times)
            intervals = intervals[intervals > 0]
            actual_rate = 1.0 / float(np.median(intervals)) if intervals.size else self.sample_rate
        else:
            actual_rate = self.sample_rate
        quality = contact_quality(ir_values, actual_rate)
        contaminated = motion | ~quality.contact_ok
        result = estimate_bpm(times, ir_values, contaminated, actual_rate)
        return (
            float(result.smoothed[-1]),
            float(result.filtered[-1]),
            bool(motion[-1]),
            float(quality.baseline[-1]),
            float(quality.pulse_amplitude[-1]),
            bool(quality.contact_ok[-1]),
            float(quality.quality_score[-1]),
            str(quality.reason[-1]),
            float(result.bpm),
            bool(result.trusted and quality.contact_ok[-1]),
        )

    def _append(self, sample):
        with self._lock:
            self._records.append(sample)

    @staticmethod
    def _csv_value(value):
        if isinstance(value, float) and not math.isfinite(value):
            return ""
        return value

    def _worker(self):
        started = time.monotonic()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_path = self.output_dir / ("heart_axi_live_{}.csv".format(stamp))
        period = 1.0 / self.sample_rate
        deadline = started
        sequence = 0
        consecutive_errors = 0

        try:
            with self.csv_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
                writer.writeheader()
                while not self._stop_event.is_set():
                    cycle_started = time.monotonic()
                    timestamp_us = time.monotonic_ns() // 1000
                    relative_time = cycle_started - started
                    self.total_cycles += 1
                    sensor_ok = False
                    fifo_ok = False
                    sample = None
                    try:
                        ir, _, overflow, _, _ = self.sensors.read_latest_ir()
                        ax_raw, ay_raw, az_raw = self.sensors.read_acceleration_raw()
                        sensor_ok = True
                        packet = pack_sample(
                            sequence, timestamp_us, ir, ax_raw, ay_raw, az_raw
                        )
                        self.fifo.round_trip(packet)
                        fifo_ok = True
                        acceleration = (
                            ax_raw / 16384.0,
                            ay_raw / 16384.0,
                            az_raw / 16384.0,
                        )
                        (
                            smooth,
                            filtered,
                            motion,
                            baseline_ir,
                            pulse_amplitude,
                            contact_ok,
                            quality_score,
                            quality_reason,
                            bpm,
                            trusted,
                        ) = self._processed_current(relative_time, ir, acceleration)
                        sample = Sample(
                            sequence=sequence,
                            timestamp_us=timestamp_us,
                            time_s=relative_time,
                            ir_raw=float(ir),
                            ir_smooth=smooth,
                            ir_filtered=filtered,
                            ax_g=acceleration[0],
                            ay_g=acceleration[1],
                            az_g=acceleration[2],
                            motion=motion,
                            baseline_ir=baseline_ir,
                            pulse_amplitude=pulse_amplitude,
                            contact_ok=contact_ok,
                            quality_score=quality_score,
                            quality_reason=quality_reason,
                            bpm=bpm,
                            trusted=trusted,
                            sensor_ok=True,
                            fifo_ok=True,
                        )
                        consecutive_errors = 0
                        self.valid_samples += 1
                        if overflow:
                            self.max_overflow_events += 1
                    except Exception as exc:
                        error_text = "{}: {}".format(type(exc).__name__, exc)
                        self.last_error = error_text
                        if not sensor_ok:
                            self.sensor_errors += 1
                        elif not fifo_ok:
                            self.fifo_errors += 1
                        consecutive_errors += 1
                        sample = Sample(
                            sequence=sequence,
                            timestamp_us=timestamp_us,
                            time_s=relative_time,
                            ir_raw=float("nan"),
                            ir_smooth=float("nan"),
                            ir_filtered=float("nan"),
                            ax_g=float("nan"),
                            ay_g=float("nan"),
                            az_g=float("nan"),
                            motion=False,
                            baseline_ir=float("nan"),
                            pulse_amplitude=float("nan"),
                            contact_ok=False,
                            quality_score=0.0,
                            quality_reason="sensor_or_fifo_error",
                            bpm=float("nan"),
                            trusted=False,
                            sensor_ok=sensor_ok,
                            fifo_ok=fifo_ok,
                            error=error_text,
                        )

                    self._append(sample)
                    row = {
                        key: self._csv_value(value)
                        for key, value in asdict(sample).items()
                    }
                    writer.writerow(row)
                    if self.total_cycles % 10 == 0:
                        csv_file.flush()
                    sequence = (sequence + 1) & 0xFFFFFFFF

                    if consecutive_errors >= 5:
                        self.state = "error"
                        self._stop_event.set()
                        break

                    deadline += period
                    delay = deadline - time.monotonic()
                    if delay > 0:
                        self._stop_event.wait(delay)
                    else:
                        self.late_cycles += 1
                        deadline = time.monotonic()
                csv_file.flush()
        except Exception as exc:
            self.last_error = "{}: {}".format(type(exc).__name__, exc)
            self.state = "error"
        finally:
            if self.state != "error":
                self.state = "stopped"
            self._finished_event.set()

    def _display_data(self):
        records = self.snapshot()
        valid = [
            record
            for record in records
            if record.sensor_ok
            and record.fifo_ok
            and math.isfinite(record.ir_raw)
            and math.isfinite(record.ax_g)
        ]
        if not valid:
            return {
                "signal": dict(t=[], raw=[], smooth=[], filtered=[], contact_y=[]),
                "peaks": dict(t=[], value=[]),
                "accel": dict(t=[], x=[], y=[], z=[], motion_y=[]),
                "bpm": float("nan"),
                "trusted": False,
                "motion": False,
                "contact_ok": False,
                "quality_score": 0.0,
                "quality_reason": "waiting_for_data",
                "rate": float("nan"),
            }

        newest = valid[-1].time_s
        valid = [record for record in valid if record.time_s >= newest - self.window_seconds]
        times = np.array([record.time_s for record in valid], dtype=float)
        raw = np.array([record.ir_raw for record in valid], dtype=float)
        x_axis = np.array([record.ax_g for record in valid], dtype=float)
        y_axis = np.array([record.ay_g for record in valid], dtype=float)
        z_axis = np.array([record.az_g for record in valid], dtype=float)
        magnitude = np.sqrt(x_axis * x_axis + y_axis * y_axis + z_axis * z_axis)
        motion = expanded_motion_mask(magnitude)
        intervals = np.diff(times)
        intervals = intervals[intervals > 0]
        rate = 1.0 / float(np.median(intervals)) if intervals.size else self.sample_rate
        quality = contact_quality(raw, rate)
        contaminated = motion | ~quality.contact_ok
        result = estimate_bpm(times, raw, contaminated, rate)
        peaks = result.peak_indices
        return {
            "signal": dict(
                t=times.tolist(),
                raw=raw.tolist(),
                smooth=result.smoothed.tolist(),
                filtered=result.filtered.tolist(),
                contact_y=np.where(~quality.contact_ok, raw, np.nan).tolist(),
            ),
            "peaks": dict(
                t=times[peaks].tolist(),
                value=result.filtered[peaks].tolist(),
            ),
            "accel": dict(
                t=times.tolist(),
                x=x_axis.tolist(),
                y=y_axis.tolist(),
                z=z_axis.tolist(),
                motion_y=np.where(motion, magnitude, np.nan).tolist(),
            ),
            "bpm": result.bpm,
            "trusted": bool(result.trusted and quality.contact_ok[-1]),
            "motion": bool(np.any(motion[-max(1, int(rate * 2)):])) if motion.size else False,
            "contact_ok": bool(quality.contact_ok[-1]),
            "quality_score": float(quality.quality_score[-1]),
            "quality_reason": str(quality.reason[-1]),
            "rate": rate,
        }

    def build_ui(self):
        from bokeh.io import output_notebook, show
        from bokeh.layouts import column
        from bokeh.models import ColumnDataSource, Div, Range1d
        from bokeh.plotting import figure
        from IPython.display import display
        import ipywidgets as widgets

        output_notebook(hide_banner=True)
        signal_source = ColumnDataSource(
            data=dict(t=[], raw=[], smooth=[], filtered=[], contact_y=[])
        )
        peak_source = ColumnDataSource(data=dict(t=[], value=[]))
        accel_source = ColumnDataSource(data=dict(t=[], x=[], y=[], z=[], motion_y=[]))
        self._sources = {
            "signal": signal_source,
            "peaks": peak_source,
            "accel": accel_source,
        }

        x_range = Range1d(0, self.window_seconds)
        self._x_range = x_range
        signal_plot = figure(
            **notebook_figure_kwargs(330),
            title="MAX30102 IR — AXI IIC + AXI FIFO verified loopback",
            x_axis_label="Time (s)",
            y_axis_label="IR",
            x_range=x_range,
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )
        signal_plot.line("t", "raw", source=signal_source, color="#ef5350", alpha=0.45,
                         legend_label="IR raw")
        signal_plot.line("t", "smooth", source=signal_source, color="#ff9800", alpha=0.8,
                         legend_label="IR smooth")
        signal_plot.scatter(
            "t",
            "contact_y",
            source=signal_source,
            color="#8e24aa",
            size=7,
            marker="circle",
            legend_label="Contact/pressure fault",
        )
        signal_plot.legend.click_policy = "hide"

        pulse_plot = figure(
            **notebook_figure_kwargs(260),
            title="0.5–2.0 Hz filtered pulse and accepted peaks",
            x_axis_label="Time (s)",
            y_axis_label="Filtered amplitude",
            x_range=x_range,
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )
        pulse_plot.line("t", "filtered", source=signal_source, color="#1565c0", line_width=2,
                        legend_label="Pulse filtered")
        pulse_plot.scatter("t", "value", source=peak_source, color="#d81b60", size=8,
                           marker="circle", legend_label="Accepted peaks")
        pulse_plot.legend.click_policy = "hide"

        accel_plot = figure(
            **notebook_figure_kwargs(280),
            title="MPU6050 acceleration and detected motion",
            x_axis_label="Time (s)",
            y_axis_label="g",
            x_range=x_range,
            tools="pan,wheel_zoom,box_zoom,reset,save",
        )
        accel_plot.line("t", "x", source=accel_source, color="#1565c0", legend_label="X")
        accel_plot.line("t", "y", source=accel_source, color="#fb8c00", legend_label="Y")
        accel_plot.line("t", "z", source=accel_source, color="#43a047", legend_label="Z")
        accel_plot.scatter("t", "motion_y", source=accel_source, color="#e53935", size=5,
                           marker="circle", legend_label="Motion")
        accel_plot.legend.click_policy = "hide"

        self._status_div = Div(
            text="Preparing acquisition…",
            **notebook_container_kwargs(),
        )
        self._motion_div = Div(
            text="",
            **notebook_container_kwargs(),
        )
        self.stop_button = widgets.Button(
            description="Stop and save CSV",
            button_style="danger",
            icon="stop",
            tooltip="Stop acquisition and close the CSV file",
        )
        self.stop_button.on_click(lambda _: self.stop())
        display(self.stop_button)
        self._handle = show(
            column(
                self._status_div,
                self._motion_div,
                signal_plot,
                pulse_plot,
                accel_plot,
                **notebook_container_kwargs(),
            ),
            notebook_handle=True,
        )
        return self

    def _refresh_ui(self):
        from bokeh.io import push_notebook

        display_data = self._display_data()
        for name in ("signal", "peaks", "accel"):
            self._sources[name].data = display_data[name]

        signal_times = display_data["signal"]["t"]
        if signal_times:
            end = signal_times[-1]
            self._x_range.start = max(0.0, end - self.window_seconds)
            self._x_range.end = max(self.window_seconds, end)

        counts = self.counters()
        bpm_text = "--" if not math.isfinite(display_data["bpm"]) else "{:.1f}".format(display_data["bpm"])
        trust_text = "可信" if display_data["trusted"] else "等待稳定数据"
        error_html = ""
        if counts["last_error"]:
            error_html = "<br><b>最近错误：</b>{}".format(html.escape(counts["last_error"]))
        self._status_div.text = (
            "<b>状态：</b>{state} &nbsp; <b>BPM：</b>{bpm} ({trust}) &nbsp; "
            "<b>采样率：</b>{rate:.2f} Hz &nbsp; <b>接触质量：</b>{quality:.0f}/100 "
            "({reason}) &nbsp; <b>有效样本：</b>{valid}/{total} &nbsp; "
            "<b>传感器错误：</b>{sensor} &nbsp; <b>FIFO错误：</b>{fifo} &nbsp; "
            "<b>CSV：</b>{csv}{error}"
        ).format(
            state=html.escape(counts["state"]),
            bpm=bpm_text,
            trust=trust_text,
            rate=display_data["rate"] if math.isfinite(display_data["rate"]) else 0.0,
            quality=display_data["quality_score"],
            reason=html.escape(display_data["quality_reason"]),
            valid=counts["valid_samples"],
            total=counts["total_cycles"],
            sensor=counts["sensor_errors"],
            fifo=counts["fifo_errors"],
            csv=html.escape(counts["csv_path"] or "creating…"),
            error=error_html,
        )
        if display_data["motion"] and not display_data["contact_ok"]:
            quality_message = (
                "<div style='padding:8px;background:#fff3e0;color:#e65100;font-weight:bold'>"
                "同时检测到运动和手指接触/压力不稳定：当前 BPM 不可信</div>"
            )
        elif display_data["motion"]:
            quality_message = (
                "<div style='padding:8px;background:#ffebee;color:#b71c1c;font-weight:bold'>"
                "检测到运动：当前 BPM 不可信</div>"
            )
        elif not display_data["contact_ok"]:
            quality_message = (
                "<div style='padding:8px;background:#f3e5f5;color:#6a1b9a;font-weight:bold'>"
                "手指压力/接触不稳定：当前 BPM 不可信</div>"
            )
        else:
            quality_message = (
                "<div style='padding:8px;background:#e8f5e9;color:#1b5e20'>"
                "运动与接触状态正常</div>"
            )
        self._motion_div.text = quality_message
        push_notebook(handle=self._handle)

    async def _ui_loop(self):
        try:
            while not self._finished_event.is_set():
                self._refresh_ui()
                await asyncio.sleep(0.25)
            self._refresh_ui()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = "UI refresh failed: {}: {}".format(type(exc).__name__, exc)
        finally:
            if self.stop_button is not None:
                self.stop_button.disabled = True
                self.stop_button.description = "Stopped — CSV saved"

    def start_ui_updates(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "A running Jupyter asyncio loop is required for live display"
            ) from exc
        self._ui_task = loop.create_task(self._ui_loop())
        return self


def _resolve_fifo_mmio(overlay, fifo_name):
    fifo_ip = getattr(overlay, fifo_name)
    if hasattr(fifo_ip, "mmio"):
        return fifo_ip.mmio
    from pynq import MMIO

    description = overlay.ip_dict[fifo_name]
    base_address = description.get("phys_addr", description.get("base_address"))
    address_range = description.get("addr_range", description.get("address_range", 0x1000))
    if base_address is None:
        raise RuntimeError("Cannot determine AXI FIFO base address from HWH metadata")
    return MMIO(int(base_address), int(address_range))


def _stop_active_monitor(timeout=5.0):
    """Stop and retire the monitor owned by this kernel before reprogramming PL."""
    global _ACTIVE_MONITOR

    with _ACTIVE_MONITOR_LOCK:
        active = _ACTIVE_MONITOR
    if active is None:
        return

    if not active.stop(wait=True, timeout=timeout):
        raise RuntimeError(
            "The previous heart monitor did not stop within {:.1f} seconds; "
            "restart the kernel before loading the overlay again.".format(timeout)
        )
    active.close_ui()
    with _ACTIVE_MONITOR_LOCK:
        if _ACTIVE_MONITOR is active:
            _ACTIVE_MONITOR = None


def start_monitor(
    bitfile="./heart_axi_iic.bit",
    output_dir=None,
    sample_rate=10.0,
    window_seconds=30.0,
):
    """Load the overlay, verify hardware, and start continuous monitoring."""
    global _ACTIVE_MONITOR

    _stop_active_monitor()
    from pynq import Overlay

    bitfile = Path(bitfile).expanduser().resolve()
    if not bitfile.exists():
        raise FileNotFoundError(str(bitfile))
    hwh_path = bitfile.with_suffix(".hwh")
    if not hwh_path.exists():
        raise FileNotFoundError(
            "Matching HWH file is required beside the bitstream: {}".format(hwh_path)
        )

    overlay = Overlay(str(bitfile))
    required = ("axi_iic_0", "axi_fifo_mm_s_0")
    missing = [name for name in required if name not in overlay.ip_dict]
    if missing:
        raise RuntimeError("Overlay is missing required IP: {}".format(", ".join(missing)))

    sensors = SensorBus(getattr(overlay, "axi_iic_0"))
    max_id, mpu_id = sensors.verify_identities()
    configuration = sensors.configure()
    fifo = AxiFifoLoopback(_resolve_fifo_mmio(overlay, "axi_fifo_mm_s_0"))
    fifo.reset()
    fifo.round_trip(pack_sample(0, time.monotonic_ns() // 1000, 0x12345, -1, 2, -3))

    print("Overlay loaded: {}".format(bitfile.name))
    print("Detected IP: {}".format(sorted(overlay.ip_dict.keys())))
    print("MAX30102 Part ID: 0x{:02X}".format(max_id))
    print("MPU6050 WHO_AM_I: 0x{:02X}".format(mpu_id))
    print(
        "MAX30102 config: FIFO=0x{fifo_config:02X}, MODE=0x{mode_config:02X}, "
        "SPO2=0x{spo2_config:02X}, LED1=0x{led1_pa:02X}, LED2=0x{led2_pa:02X}".format(
            **configuration
        )
    )
    print("AXI FIFO startup loopback: PASS")

    monitor = HeartAxiMonitor(
        sensors=sensors,
        fifo=fifo,
        output_dir=output_dir or bitfile.parent,
        sample_rate=sample_rate,
        window_seconds=window_seconds,
    )
    try:
        monitor.build_ui()
        monitor.start()
        monitor.start_ui_updates()
    except Exception:
        monitor.stop(wait=True, timeout=5.0)
        monitor.close_ui()
        raise
    with _ACTIVE_MONITOR_LOCK:
        _ACTIVE_MONITOR = monitor
    return monitor


__all__ = [
    "AxiFifoLoopback",
    "ContactQualityResult",
    "HeartAxiMonitor",
    "HeartRateResult",
    "Sample",
    "SensorBus",
    "contact_quality",
    "estimate_bpm",
    "expanded_motion_mask",
    "fifo_available",
    "pack_sample",
    "signed16",
    "start_monitor",
]
