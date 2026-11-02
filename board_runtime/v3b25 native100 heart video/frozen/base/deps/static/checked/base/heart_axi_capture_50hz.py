"""Headless, loss-accounted 50 Hz sensor capture for the V2 acquisition gate."""

import csv
import json
import math
import time
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from heart_axi_live import (
    AxiFifoLoopback,
    SensorBus,
    _resolve_fifo_mmio,
    max30102_fifo_config,
    pack_sample,
)


TARGET_RATE_HZ = 50.0
SAMPLE_PERIOD_US = int(round(1_000_000 / TARGET_RATE_HZ))
# 连续100次三轴原始整数完全相同：50Hz下约2秒，标为疑似陈旧，不断言硬件根因。
ACCEL_REPEAT_LIMIT = 100


@dataclass(frozen=True)
class CapturePhase:
    index: int
    label: str
    start_s: float
    end_s: float
    instruction: str


V2_MOTION_PROTOCOL_NAME = "v2_motion_20_20_20"
V2_MOTION_DURATION_SECONDS = 60.0
V2_MOTION_PHASES = (
    CapturePhase(0, "still_before", 0.0, 20.0, "保持静止"),
    CapturePhase(1, "light_motion", 20.0, 40.0, "开始轻微横向往复晃动"),
    CapturePhase(2, "still_after", 40.0, 60.0, "停止晃动并保持静止"),
)


def validate_phase_schedule(phases, duration_seconds):
    phases = tuple(phases)
    if not phases:
        raise ValueError("phase schedule must not be empty")
    if phases[0].start_s != 0.0:
        raise ValueError("phase schedule must start at 0 seconds")
    labels = set()
    previous_end = 0.0
    for expected_index, phase in enumerate(phases):
        if phase.index != expected_index:
            raise ValueError("phase indices must be consecutive from zero")
        if not phase.label or phase.label in labels:
            raise ValueError("phase labels must be non-empty and unique")
        if phase.start_s != previous_end:
            raise ValueError("phase schedule must be continuous")
        if phase.end_s <= phase.start_s:
            raise ValueError("phase duration must be positive")
        labels.add(phase.label)
        previous_end = phase.end_s
    if previous_end != float(duration_seconds):
        raise ValueError("phase schedule must end at capture duration")
    return phases


def phase_for_time(phases, time_s):
    phases = tuple(phases)
    time_s = float(time_s)
    for phase in phases[:-1]:
        if time_s < phase.end_s:
            return phase, time_s - phase.start_s
    phase = phases[-1]
    return phase, time_s - phase.start_s


RAW_CSV_FIELDS = (
    "sequence",
    "timestamp_us",
    "read_timestamp_us",
    "nominal_timestamp_us",
    "timestamp_policy",
    "time_s",
    "ir_raw",
    "ax_g",
    "ay_g",
    "az_g",
    "pair_ok",
    "accel_valid",
    "mpu_ax_raw",
    "mpu_ay_raw",
    "mpu_az_raw",
    "accel_repeat_count",
    "fifo_batch_size",
    "max30102_overflow",
    "pl_fifo_ok",
    "error",
    "phase",
    "phase_index",
    "phase_elapsed_s",
)


def reconstruct_batch_timestamps(batch_size, read_timestamp_us, previous_timestamp_us):
    """按观察区间保序；异常批次的内插时间不是实际 ADC 采样时间。"""
    if batch_size <= 0:
        return (), (), "nominal_backprojection"
    nominal = tuple(
        read_timestamp_us - (batch_size - 1 - index) * SAMPLE_PERIOD_US
        for index in range(batch_size)
    )
    if nominal[0] > previous_timestamp_us:
        return nominal, nominal, "nominal_backprojection"
    interval = read_timestamp_us - previous_timestamp_us
    if interval < batch_size:
        raise ValueError("timestamp interval cannot contain this batch in strict order")
    # 保留全部原始 PPG，但不假造未来时间，也不声称这些点仍具有 20ms 间隔。
    timestamps = tuple(
        previous_timestamp_us + interval * (index + 1) // batch_size
        for index in range(batch_size)
    )
    return timestamps, nominal, "compressed_observation_interval"


def expected_50hz_registers():
    """Return the MAX30102 readback required by the 50 Hz capture mode."""
    return {
        "fifo_config": max30102_fifo_config(sample_average=1, almost_full=15),
        "spo2_config": 0x23,
        "mpu_sample_rate_divider": 19,
        "mpu_dlpf_config": 4,
        "mpu_accel_config": 0,
    }


def validate_50hz_registers(configuration):
    """Reject a capture if the sensor did not accept the 50 Hz settings."""
    expected = expected_50hz_registers()
    actual_fifo = configuration.get("fifo_config")
    if actual_fifo != expected["fifo_config"]:
        raise RuntimeError(
            "MAX30102 FIFO_CONFIG expected 0x{:02X}, got {}".format(
                expected["fifo_config"],
                "missing" if actual_fifo is None else "0x{:02X}".format(actual_fifo),
            )
        )
    actual_spo2 = configuration.get("spo2_config")
    if actual_spo2 != expected["spo2_config"]:
        raise RuntimeError(
            "MAX30102 SPO2_CONFIG expected 0x{:02X}, got {}".format(
                expected["spo2_config"],
                "missing" if actual_spo2 is None else "0x{:02X}".format(actual_spo2),
            )
        )
    mpu_registers = (
        ("mpu_sample_rate_divider", "MPU6050 SMPLRT_DIV"),
        ("mpu_dlpf_config", "MPU6050 CONFIG"),
        ("mpu_accel_config", "MPU6050 ACCEL_CONFIG"),
    )
    for key, label in mpu_registers:
        actual = configuration.get(key)
        if actual != expected[key]:
            raise RuntimeError(
                "{} expected 0x{:02X}, got {}".format(
                    label,
                    expected[key],
                    "missing" if actual is None else "0x{:02X}".format(actual),
                )
            )
    return True


class RawCapture50Hz:
    """Capture raw FIFO records without plotting or windowed signal processing."""

    def __init__(self, sensors, fifo, output_dir=".", clock=time):
        self.sensors = sensors
        self.fifo = fifo
        self.clock = clock
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        stem = "heart_axi_capture_50hz_{}".format(stamp)
        self.csv_path = self.output_dir / (stem + ".csv")
        self.summary_path = self.output_dir / (stem + ".json")
        self.summary = {}

    @staticmethod
    def _empty_acceleration():
        return "", "", ""

    @staticmethod
    def _acceleration_g(raw):
        return tuple(value / 16384.0 for value in raw)

    def _diagnostic_snapshot(self):
        """只在停止采集后只读检查；总线再次报错即停止额外读取。"""
        reader = getattr(self.sensors, "read_register", None)
        if reader is None:
            return {"available": False}
        result = {"available": True, "registers": {}}
        for name, address, register in (
            ("mpu_who_am_i", 0x68, 0x75),
            ("mpu_power", 0x68, 0x6B),
            ("mpu_sample_divider", 0x68, 0x19),
            ("mpu_dlpf", 0x68, 0x1A),
            ("mpu_accel_config", 0x68, 0x1C),
            ("max_part_id", 0x57, 0xFF),
        ):
            try:
                result["registers"][name] = int(reader(address, register))
            except Exception as exc:
                result["read_error"] = {
                    "register": name, "exception_type": type(exc).__name__, "message": str(exc)
                }
                break
        return result

    def run(
        self,
        duration_seconds=None,
        max_samples=None,
        phase_schedule=None,
        protocol_name="",
        prestart_countdown_seconds=0,
    ):
        """Run a bounded capture and always finalize the CSV and summary JSON."""
        if duration_seconds is None and max_samples is None:
            raise ValueError("duration_seconds or max_samples is required")
        if duration_seconds is not None and float(duration_seconds) <= 0:
            raise ValueError("duration_seconds must be positive")
        if max_samples is not None and int(max_samples) <= 0:
            raise ValueError("max_samples must be positive")
        phase_schedule = tuple(phase_schedule or ())
        if phase_schedule:
            if duration_seconds is None:
                raise ValueError("labeled capture requires duration_seconds")
            phase_schedule = validate_phase_schedule(phase_schedule, duration_seconds)
        prestart_countdown_seconds = int(prestart_countdown_seconds)
        if prestart_countdown_seconds < 0:
            raise ValueError("prestart_countdown_seconds must not be negative")

        started_monotonic = None
        started_ns = None
        sequence = 0
        total_samples = 0
        paired_samples = 0
        unpaired_samples = 0
        max_fifo_batch = 0
        overflow_events = 0
        overflow_count = 0
        sensor_errors = 0
        pl_fifo_errors = 0
        stopped_by_keyboard = False
        startup_discarded_samples = 0
        startup_overflow_count = 0
        timestamp_overlap_batches = 0
        timestamp_compressed_samples = 0
        timestamp_errors = 0
        timestamp_rejected_samples = 0
        phase_sample_counts = {phase.label: 0 for phase in phase_schedule}
        announced_phase_index = None
        diagnostic_events = []
        acceleration_invalid_events = 0
        previous_acceleration_raw = None
        acceleration_repeat_count = 0
        max_acceleration_repeat_count = 0
        stop_reason = ""
        stage = "startup_fifo_clear"

        def record_fault(reason, exc=None, raw=None, consumed_ppg=0):
            event = {
                "stage": stage,
                "reason": reason,
                "sequence": sequence,
                "elapsed_seconds": (
                    self.clock.monotonic() - started_monotonic
                    if started_monotonic is not None else None
                ),
                "exception_type": type(exc).__name__ if exc is not None else None,
                "message": str(exc) if exc is not None else reason,
                "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) if exc is not None else "",
                "acceleration_raw": list(raw) if raw is not None else None,
                "consumed_ppg_samples": consumed_ppg,
                "register_snapshot": self._diagnostic_snapshot(),
            }
            diagnostic_events.append(event)
            print("采集异常，停止本次实验：{}，阶段：{}".format(reason, stage))

        try:
            with self.csv_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=RAW_CSV_FIELDS)
                writer.writeheader()
                for remaining in range(prestart_countdown_seconds, 0, -1):
                    print("正式采集将在 {} 秒后开始".format(remaining))
                    self.clock.sleep(1.0)
                self.sensors.clear_max30102_fifo()
                stage = "startup_fifo_discard"
                startup_batch = self.sensors.read_fifo_ir_samples(timeout=0.5)
                startup_discarded_samples = len(startup_batch.ir_samples)
                startup_overflow_count = int(startup_batch.overflow)
                started_monotonic = self.clock.monotonic()
                started_ns = self.clock.monotonic_ns()
                previous_timestamp_us = started_ns // 1000
                while True:
                    elapsed = self.clock.monotonic() - started_monotonic
                    if duration_seconds is not None and elapsed >= float(duration_seconds):
                        break
                    if max_samples is not None and total_samples >= int(max_samples):
                        break

                    try:
                        stage = "max30102_fifo_read"
                        batch = self.sensors.read_fifo_ir_samples(timeout=0.5)
                        read_timestamp_ns = self.clock.monotonic_ns()
                    except KeyboardInterrupt:
                        stopped_by_keyboard = True
                        break
                    except Exception as exc:
                        sensor_errors += 1
                        stop_reason = "sensor_read_exception"
                        record_fault(stop_reason, exc)
                        break

                    stage = "mpu_acceleration_read"
                    acceleration_raw = None
                    acceleration_g = self._empty_acceleration()
                    accel_valid = False
                    acceleration_error = ""
                    try:
                        acceleration_raw = tuple(self.sensors.read_acceleration_raw())
                        if len(acceleration_raw) != 3 or any(
                            not isinstance(value, int) or not -32768 <= value <= 32767
                            for value in acceleration_raw
                        ):
                            raise ValueError("invalid MPU6050 raw acceleration format")
                        if acceleration_raw == previous_acceleration_raw:
                            acceleration_repeat_count += 1
                        else:
                            acceleration_repeat_count = 1
                        previous_acceleration_raw = acceleration_raw
                        max_acceleration_repeat_count = max(
                            max_acceleration_repeat_count, acceleration_repeat_count
                        )
                        if acceleration_raw == (0, 0, 0):
                            stop_reason = "acceleration_all_zero"
                        elif acceleration_repeat_count >= ACCEL_REPEAT_LIMIT:
                            stop_reason = "acceleration_repeated_suspected_stale"
                        else:
                            acceleration_g = self._acceleration_g(acceleration_raw)
                            accel_valid = True
                        if not accel_valid:
                            acceleration_invalid_events += 1
                            acceleration_error = stop_reason
                            record_fault(stop_reason, raw=acceleration_raw, consumed_ppg=len(batch.ir_samples))
                    except KeyboardInterrupt:
                        stopped_by_keyboard = True
                        break
                    except Exception as exc:
                        sensor_errors += 1
                        acceleration_invalid_events += 1
                        stop_reason = "sensor_read_exception"
                        acceleration_error = "{}: {}".format(type(exc).__name__, exc)
                        record_fault(stop_reason, exc, acceleration_raw, len(batch.ir_samples))

                    batch_size = len(batch.ir_samples)
                    max_fifo_batch = max(max_fifo_batch, batch_size)
                    if batch.overflow:
                        overflow_events += 1
                        overflow_count += int(batch.overflow)

                    read_timestamp_us = read_timestamp_ns // 1000
                    try:
                        timestamps, nominal_timestamps, timestamp_policy = (
                            reconstruct_batch_timestamps(
                                batch_size, read_timestamp_us, previous_timestamp_us
                            )
                        )
                    except ValueError:
                        timestamp_errors += 1
                        timestamp_rejected_samples += batch_size
                        # 无法保序时终止并保存诊断，不默默删点后继续宣称采集正常。
                        raise
                    if timestamp_policy == "compressed_observation_interval":
                        timestamp_overlap_batches += 1
                        timestamp_compressed_samples += max(0, batch_size - 1)
                    for index, ir_raw in enumerate(batch.ir_samples):
                        newest = index == batch_size - 1
                        timestamp_us = timestamps[index]
                        pair_ok = bool(newest and accel_valid)
                        pl_fifo_ok = ""
                        error = acceleration_error if newest else ""
                        if pair_ok:
                            ax_g, ay_g, az_g = acceleration_g
                            packet = pack_sample(
                                sequence,
                                timestamp_us,
                                int(ir_raw),
                                acceleration_raw[0],
                                acceleration_raw[1],
                                acceleration_raw[2],
                            )
                            try:
                                pl_fifo_ok = self.fifo.round_trip(packet) == packet
                            except Exception as exc:
                                pl_fifo_ok = False
                                error = "{}: {}".format(type(exc).__name__, exc)
                            if not pl_fifo_ok:
                                pl_fifo_errors += 1
                            paired_samples += 1
                        else:
                            ax_g, ay_g, az_g = self._empty_acceleration()
                            unpaired_samples += 1

                        sample_time_s = (
                            timestamp_us - started_ns // 1000
                        ) / 1_000_000
                        if phase_schedule:
                            phase, phase_elapsed_s = phase_for_time(
                                phase_schedule, sample_time_s
                            )
                            phase_label = phase.label
                            phase_index = phase.index
                            phase_sample_counts[phase.label] += 1
                            if announced_phase_index != phase.index:
                                print(
                                    "阶段 {}：{}".format(
                                        phase.index + 1, phase.instruction
                                    )
                                )
                                announced_phase_index = phase.index
                        else:
                            phase_label = ""
                            phase_index = ""
                            phase_elapsed_s = ""

                        writer.writerow(
                            {
                                "sequence": sequence,
                                "timestamp_us": timestamp_us,
                                "read_timestamp_us": read_timestamp_us,
                                "nominal_timestamp_us": nominal_timestamps[index],
                                "timestamp_policy": timestamp_policy,
                                "time_s": sample_time_s,
                                "ir_raw": int(ir_raw),
                                "ax_g": ax_g,
                                "ay_g": ay_g,
                                "az_g": az_g,
                                "pair_ok": pair_ok,
                                "accel_valid": bool(newest and accel_valid),
                                "mpu_ax_raw": acceleration_raw[0] if newest and acceleration_raw is not None and len(acceleration_raw)==3 else "",
                                "mpu_ay_raw": acceleration_raw[1] if newest and acceleration_raw is not None and len(acceleration_raw)==3 else "",
                                "mpu_az_raw": acceleration_raw[2] if newest and acceleration_raw is not None and len(acceleration_raw)==3 else "",
                                "accel_repeat_count": acceleration_repeat_count if newest else "",
                                "fifo_batch_size": batch_size,
                                "max30102_overflow": int(batch.overflow),
                                "pl_fifo_ok": pl_fifo_ok,
                                "error": error,
                                "phase": phase_label,
                                "phase_index": phase_index,
                                "phase_elapsed_s": phase_elapsed_s,
                            }
                        )
                        sequence = (sequence + 1) & 0xFFFFFFFF
                        total_samples += 1
                        previous_timestamp_us = timestamp_us

                    if total_samples and total_samples % 50 == 0:
                        csv_file.flush()
                    if stop_reason:
                        break
                csv_file.flush()
        except KeyboardInterrupt:
            stopped_by_keyboard = True
        except Exception as exc:
            stop_reason = "capture_exception"
            if not diagnostic_events:
                record_fault(stop_reason, exc)
            raise
        finally:
            elapsed_seconds = (
                max(0.0, self.clock.monotonic() - started_monotonic)
                if started_monotonic is not None
                else 0.0
            )
            pair_ratio = (
                paired_samples / total_samples if total_samples else 0.0
            )
            self.summary = {
                "target_rate_hz": TARGET_RATE_HZ,
                "fifo_sample_average": 1,
                "total_ppg_samples": total_samples,
                "paired_samples": paired_samples,
                "unpaired_samples": unpaired_samples,
                "pair_ratio": pair_ratio,
                "elapsed_seconds": elapsed_seconds,
                "actual_rate_hz": (
                    total_samples / elapsed_seconds if elapsed_seconds else math.nan
                ),
                "max_fifo_batch": max_fifo_batch,
                "max30102_overflow_events": overflow_events,
                "max30102_overflow_count": overflow_count,
                "sensor_errors": sensor_errors,
                "acquisition_status": (
                    "rejected" if stop_reason or sensor_errors or acceleration_invalid_events
                    or timestamp_errors or pl_fifo_errors or overflow_events
                    else "interrupted" if stopped_by_keyboard
                    else "completed_without_detected_errors"
                ),
                "stop_reason": stop_reason or ("keyboard_interrupt" if stopped_by_keyboard else "limit_reached"),
                "diagnostic_version": 1,
                "diagnostic_events": diagnostic_events,
                "acceleration_invalid_events": acceleration_invalid_events,
                "acceleration_repeat_limit": ACCEL_REPEAT_LIMIT,
                "max_acceleration_repeat_count": max_acceleration_repeat_count,
                "pl_fifo_errors": pl_fifo_errors,
                "startup_discarded_samples": startup_discarded_samples,
                "startup_overflow_count": startup_overflow_count,
                "timestamp_reconstruction_version": 2,
                "timestamp_overlap_batches": timestamp_overlap_batches,
                "timestamp_compressed_samples": timestamp_compressed_samples,
                "timestamp_errors": timestamp_errors,
                "timestamp_rejected_samples": timestamp_rejected_samples,
                "stopped_by_keyboard": stopped_by_keyboard,
                "csv_path": str(self.csv_path),
                "protocol_name": str(protocol_name) if phase_schedule else "",
                "protocol_duration_seconds": (
                    float(duration_seconds) if phase_schedule else None
                ),
                "protocol_phases": [
                    {
                        "index": phase.index,
                        "label": phase.label,
                        "start_s": phase.start_s,
                        "end_s": phase.end_s,
                        "instruction": phase.instruction,
                    }
                    for phase in phase_schedule
                ],
                "phase_sample_counts": phase_sample_counts,
                "prestart_countdown_seconds": prestart_countdown_seconds,
            }
            with self.summary_path.open("w", encoding="utf-8") as summary_file:
                json.dump(self.summary, summary_file, ensure_ascii=False, indent=2)
                summary_file.write("\n")
        return self


def run_50hz_capture(
    bitfile="./heart_axi_iic.bit",
    output_dir=None,
    duration_seconds=60.0,
    phase_schedule=None,
    protocol_name="",
    prestart_countdown_seconds=0,
):
    """Load the overlay and run one bounded, headless 50 Hz capture."""
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
    configuration = sensors.configure(
        fifo_sample_average=1,
        mpu_sample_rate_hz=50,
        mpu_dlpf_cfg=4,
    )
    validate_50hz_registers(configuration)

    fifo = AxiFifoLoopback(_resolve_fifo_mmio(overlay, "axi_fifo_mm_s_0"))
    fifo.reset()
    startup_packet = pack_sample(0, time.monotonic_ns() // 1000, 0x12345, -1, 2, -3)
    if fifo.round_trip(startup_packet) != startup_packet:
        raise RuntimeError("AXI FIFO startup loopback mismatch")
    print("Overlay loaded: {}".format(bitfile.name))
    print("MAX30102 Part ID: 0x{:02X}".format(max_id))
    print("MPU6050 WHO_AM_I: 0x{:02X}".format(mpu_id))
    print(
        "50 Hz config: FIFO=0x{fifo_config:02X}, SPO2=0x{spo2_config:02X}".format(
            **configuration
        )
    )
    print("AXI FIFO startup loopback: PASS")

    capture = RawCapture50Hz(
        sensors=sensors,
        fifo=fifo,
        output_dir=output_dir or bitfile.parent,
    )
    return capture.run(
        duration_seconds=duration_seconds,
        phase_schedule=phase_schedule,
        protocol_name=protocol_name,
        prestart_countdown_seconds=prestart_countdown_seconds,
    )


def run_v2_motion_protocol(
    bitfile="./heart_axi_iic.bit",
    output_dir=None,
    prestart_countdown_seconds=5,
):
    """Run the fixed 20 s still, 20 s light-motion, 20 s still protocol."""
    print("V2 协议：20秒静止，20秒轻晃，20秒静止")
    print("轻晃时保持接触压力，不要抬起或重新放置手指")
    return run_50hz_capture(
        bitfile=bitfile,
        output_dir=output_dir,
        duration_seconds=V2_MOTION_DURATION_SECONDS,
        phase_schedule=V2_MOTION_PHASES,
        protocol_name=V2_MOTION_PROTOCOL_NAME,
        prestart_countdown_seconds=prestart_countdown_seconds,
    )
