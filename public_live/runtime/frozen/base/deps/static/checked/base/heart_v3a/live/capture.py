"""复用只读传感器基础接口，不下载旧Overlay、不复制历史加速度。"""
import time
from heart_axi_capture_50hz import ACCEL_REPEAT_LIMIT, reconstruct_batch_timestamps
from heart_axi_live import pack_sample
from .contracts import LiveBatch, LiveFault, LiveRecord


def phase_at(protocol, time_s):
    if protocol == "motion":
        index = 0 if time_s < 20 else 1 if time_s < 40 else 2
        return ("still_before", "light_motion", "still_after")[index], index, time_s - (0, 20, 40)[index]
    if protocol == "contact":
        index = 0 if time_s < 20 else 1 if time_s < 30 else 2
        return ("contact_good", "contact_removed", "contact_recovery")[index], index, time_s - (0, 20, 30)[index]
    return "static", 0, time_s


class CaptureAdapter:
    def __init__(self, sensors, fifo, *, protocol, clock=time):
        if protocol not in ("static", "motion", "contact"):
            raise ValueError("采集协议不合法")
        self.sensors, self.fifo, self.protocol, self.clock = sensors, fifo, protocol, clock
        self._begun = False
        self._fault = None
        self._capture_stopped = False
        self._sequence = 0
        self._batch_id = 0
        self._previous_acceleration = None
        self._repeat_count = 0

    def begin(self):
        if self._begun:
            raise RuntimeError("采集适配器仅能启动一次")
        self._begun = True
        self.sensors.clear_max30102_fifo()
        startup = self.sensors.read_fifo_ir_samples(timeout=0.5)
        self.started_ns = self.clock.monotonic_ns()
        self._previous_timestamp_us = self.started_ns // 1000
        return dict(startup_discarded_samples=len(startup.ir_samples),
            startup_overflow_count=int(startup.overflow), started_ns=self.started_ns)

    def _make_fault(self, stage, reason, count, exc=None, unknown=False):
        if self._fault is None:
            self._fault = LiveFault(stage, reason, self._sequence, self.clock.monotonic_ns(),
                dict(consumed_ppg_samples=count, consumed_ppg_unknown=unknown,
                    exception_type=type(exc).__name__ if exc else None, message=str(exc) if exc else reason))
        return self._fault

    def read_batch(self):
        if not self._begun or self._fault or self._capture_stopped:
            raise RuntimeError("采集未启动或已锁定停止")
        loop_started = self.clock.monotonic_ns()
        try:
            batch = self.sensors.read_fifo_ir_samples(timeout=0.5)
        except Exception as exc:
            fault = self._make_fault("max30102_fifo_read", "sensor_read_exception", 0, exc, unknown=True)
            return LiveBatch(self._batch_id, (), self.clock.monotonic_ns(), fault)
        read_ns = self.clock.monotonic_ns()
        size = len(batch.ir_samples)
        if not 0 < size <= 32:
            fault = self._make_fault("max30102_fifo_read", "invalid_fifo_batch_size", size)
            return LiveBatch(self._batch_id, (), read_ns, fault)
        acceleration = None
        accel_valid = False
        try:
            acceleration = tuple(self.sensors.read_acceleration_raw())
            if len(acceleration) != 3 or any(type(v) is not int or not -32768 <= v <= 32767 for v in acceleration):
                raise ValueError("MPU加速度不是三路signed16整数")
            self._repeat_count = self._repeat_count + 1 if acceleration == self._previous_acceleration else 1
            self._previous_acceleration = acceleration
            if acceleration == (0, 0, 0):
                self._make_fault("mpu_acceleration_read", "acceleration_all_zero", size)
            elif self._repeat_count >= ACCEL_REPEAT_LIMIT:
                self._make_fault("mpu_acceleration_read", "acceleration_repeated_suspected_stale", size)
            else:
                accel_valid = True
        except Exception as exc:
            self._make_fault("mpu_acceleration_read", "sensor_read_exception", size, exc)
        mpu_ns = self.clock.monotonic_ns()
        if batch.overflow:
            self._make_fault("max30102_fifo_read", "max30102_overflow", size)
        if self._sequence + size - 1 > 0xFFFFFFFF:
            self._make_fault("sequence", "sequence_range_exhausted", size)
        try:
            stamps, nominal, policy = reconstruct_batch_timestamps(size, read_ns // 1000, self._previous_timestamp_us)
        except ValueError as exc:
            stamps, nominal, policy = ("",) * size, ("",) * size, "invalid_observation_interval"
            self._make_fault("timestamp_reconstruction", "timestamp_reconstruction_error", size, exc)
        loopback = ""
        if accel_valid and self._fault is None:
            packet = pack_sample(self._sequence + size - 1, stamps[-1], int(batch.ir_samples[-1]), *acceleration)
            try:
                loopback = self.fifo.round_trip(packet) == packet
                if not loopback:
                    self._make_fault("axi_fifo_loopback", "pl_fifo_error", size)
            except Exception as exc:
                loopback = False
                self._make_fault("axi_fifo_loopback", "pl_fifo_error", size, exc)
        records = []
        loop_ns = self.clock.monotonic_ns() - loop_started
        for index, ir in enumerate(batch.ir_samples):
            newest = index == size - 1
            paired = newest and accel_valid
            axes = tuple(v / 16384 for v in acceleration) if paired else ("", "", "")
            relative = (stamps[index] - self.started_ns // 1000) / 1e6 if stamps[index] != "" else ""
            phase, phase_index, phase_elapsed = phase_at(self.protocol, relative) if relative != "" else ("", "", "")
            raw_axes = acceleration if newest and acceleration is not None and len(acceleration) == 3 else ("", "", "")
            # 非法原始轴照实保留以便诊断，不赋予有效配对许可。
            row = dict(sequence=self._sequence, timestamp_us=stamps[index], read_timestamp_us=read_ns // 1000,
                nominal_timestamp_us=nominal[index], timestamp_policy=policy, time_s=relative,
                ir_raw=int(ir), ax_g=axes[0], ay_g=axes[1], az_g=axes[2], pair_ok=paired,
                accel_valid=paired, mpu_ax_raw=raw_axes[0], mpu_ay_raw=raw_axes[1], mpu_az_raw=raw_axes[2],
                accel_repeat_count=self._repeat_count if newest else "", fifo_batch_size=size,
                max30102_overflow=int(batch.overflow), pl_fifo_ok=loopback if newest else "",
                error=self._fault.reason if self._fault else "", phase=phase,
                phase_index=phase_index, phase_elapsed_s=phase_elapsed, batch_id=self._batch_id,
                max_write_pointer=int(batch.write_pointer), max_read_pointer=int(batch.read_pointer),
                max_available=int(batch.available), ppg_read_completed_ns=read_ns,
                mpu_read_completed_ns=mpu_ns, capture_loop_ns=loop_ns)
            records.append(LiveRecord(row, read_ns))
            self._sequence += 1
        if stamps[-1] != "":
            self._previous_timestamp_us = stamps[-1]
        result = LiveBatch(self._batch_id, tuple(records), self.clock.monotonic_ns(), self._fault)
        self._batch_id += 1
        return result

    def diagnostic_snapshot(self):
        if not self._capture_stopped:
            raise RuntimeError("尚未确认采集线程停止，不执行额外I²C诊断")
        reader = getattr(self.sensors, "read_register", None)
        if reader is None:
            return dict(available=False)
        result = dict(available=True, registers={})
        for name, address, register in (("mpu_who_am_i", 0x68, 0x75), ("mpu_power", 0x68, 0x6B),
            ("mpu_sample_divider", 0x68, 0x19), ("mpu_dlpf", 0x68, 0x1A),
            ("mpu_accel_config", 0x68, 0x1C), ("max_part_id", 0x57, 0xFF)):
            try:
                result["registers"][name] = int(reader(address, register))
            except Exception as exc:
                result["read_error"] = dict(register=name, exception_type=type(exc).__name__, message=str(exc))
                break
        return result
