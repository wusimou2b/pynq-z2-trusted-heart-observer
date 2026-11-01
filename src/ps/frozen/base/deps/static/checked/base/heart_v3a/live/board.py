"""显式板端边界和结束后的文件审计；默认不导入PYNQ。"""
import csv
from dataclasses import dataclass
import hashlib
import inspect
import json
import math
from pathlib import Path
import re
import sys
import numpy as np
from .contracts import LiveSettings, frozen, finite, plain
from .session import LiveSession

PERFORMANCE_FIELDS = ("record_rate_hz_min", "record_rate_hz_max", "read_gap_p99_ms_max",
    "read_gap_max_ms_max", "capture_loop_overrun_fraction_max", "read_to_result_p99_ms_max",
    "read_to_result_max_ms_max", "read_to_display_p99_ms_max", "read_to_display_max_ms_max")
IDENTITY_FIELDS = ("base_manifest_sha256", "bit_sha256", "hwh_sha256")


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _validated_bundle(path):
    from heart_v3a.live_delivery import validate_live_bundle
    return validate_live_bundle(path)


@dataclass(frozen=True)
class FrozenLimits:
    document: object
    sha256: str


def load_limits(path, *, identity=None):
    path = Path(path)
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("schema") != "v3a_live_limits_v1" or doc.get("approved") is not True:
        raise ValueError("限值schema／明确批准不合法")
    if not isinstance(doc.get("approved_at"), str) or not doc["approved_at"].strip():
        raise ValueError("限值缺少整体批准记录")
    hashes = [doc.get(key) for key in IDENTITY_FIELDS]
    sources = doc.get("baseline_sources", {})
    hashes += [sources.get(key) for key in ("raw_sha256", "summary_sha256")]
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value) for value in hashes):
        raise ValueError("限值必须有基准来源及设备身份SHA256")
    if identity is not None and any(doc[key] != identity.get(key) for key in IDENTITY_FIELDS):
        raise ValueError("限值与本交付设备身份不符")
    values = doc.get("performance", {})
    if set(values) != set(PERFORMANCE_FIELDS):
        raise ValueError("性能限值字段不完整／包含未知字段")
    for key in PERFORMANCE_FIELDS:
        value = finite(values[key], key)
        if value < 0 or key.startswith("record_rate") and value <= 0:
            raise ValueError("性能限值不能为负／记录率须为正")
    if values["record_rate_hz_min"] > values["record_rate_hz_max"] or values["capture_loop_overrun_fraction_max"] > 1:
        raise ValueError("限值上下界／比例不合法")
    for stem in ("read_gap", "read_to_result", "read_to_display"):
        if values[stem + "_p99_ms_max"] > values[stem + "_max_ms_max"]:
            raise ValueError("p99限值不能高于最大值限值")
    return FrozenLimits(frozen(doc), _digest(path))


class BoardLease:
    def __init__(self, path="/tmp/heart_v3a_live.lock"):
        self.path, self.stream = Path(path), None

    def acquire(self):
        if sys.platform != "linux":
            raise RuntimeError("真实硬件入口仅支持板端Linux")
        if self.stream is not None:
            raise RuntimeError("锁已持有")
        import fcntl
        stream = self.path.open("a", encoding="utf-8")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException as exc:
            stream.close()
            raise RuntimeError("另一进程持有实时硬件锁") from exc
        self.stream = stream

    def release(self):
        if self.stream is not None:
            import fcntl
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None


def check_lock_exclusion():
    """只检查Linux两进程文件锁；不加载Overlay。"""
    import subprocess
    # 子进程只用标准库；不能把整条算法的冷启动导入计入5秒锁检查。
    # 3仅表示真实锁竞争，其他异常退出不能冒充“锁忙”。
    code = """import fcntl, sys
with open(sys.argv[1], "a", encoding="utf-8") as stream:
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(3)
    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
"""
    lease = BoardLease()
    lease.acquire()
    command = [sys.executable, "-c", code, str(lease.path)]
    try:
        blocked = subprocess.run(command, capture_output=True, timeout=5)
    finally:
        lease.release()
    free = subprocess.run(command, capture_output=True, timeout=5)
    if blocked.returncode != 3 or free.returncode != 0:
        raise RuntimeError("Linux跨进程锁竞争／释放检查失败")
    return dict(lock_competition_passed=True, hardware_loaded=False)


def validate_output(bundle, output_dir):
    bundle, path = Path(bundle).resolve(), Path(output_dir).resolve()
    if path.exists():
        raise ValueError("已有会话目录不得覆盖")
    if path.is_relative_to(bundle):
        relative = path.relative_to(bundle)
        if not relative.parts or relative.parts[0] != "live_results":
            raise ValueError("输出不得覆盖交付追踪文件／provenance")
    return path


def prepare_live_session(bundle, output_dir, settings, *, hardware=False, limits_path=None,
                         session_factory=LiveSession):
    if hardware is not True:
        raise ValueError("必须显式确认hardware=True才可准备板端")
    if not isinstance(settings, LiveSettings):
        raise ValueError("设置必须为LiveSettings")
    if settings.mode == "acceptance" and limits_path is None:
        raise ValueError("正式验收必须先提供经基准确认的限值文件")
    limits = load_limits(limits_path) if limits_path is not None else None
    bundle = Path(bundle).resolve()
    identity = _validated_bundle(bundle)
    if limits is not None:
        limits = load_limits(limits_path, identity=identity)
    output = validate_output(bundle, output_dir)
    if sys.platform != "linux":
        raise RuntimeError("真实硬件入口仅支持板端Linux")
    session = session_factory(None, None, output, settings)
    session._claim_owner()
    try:
        lease = BoardLease()
        session._board_lease = lease
        lease.acquire()
        from pynq import Overlay, MMIO
        from heart_axi_live import SensorBus, AxiFifoLoopback, _resolve_fifo_mmio, pack_sample
        from heart_axi_capture_50hz import validate_50hz_registers
        from heart_v3a.axi_contract import BASE_ADDRESS, ADDRESS_RANGE
        from heart_v3a.axi_driver import NlmsAxiDriver
        from .capture import CaptureAdapter
        overlay = Overlay(str(bundle / "heart_v3a.bit"))
        addresses = {"axi_iic_0": (0x41600000, "xilinx.com:ip:axi_iic:2.1"),
            "axi_fifo_mm_s_0": (0x43c00000, "xilinx.com:ip:axi_fifo_mm_s:4.3"),
            "nlms_axi_0": (0x43c10000, "heart.local:signal:nlms_axi_lite:1.0")}
        for name, (base, kind) in addresses.items():
            ip = overlay.ip_dict.get(name, {})
            if (ip.get("phys_addr"), ip.get("addr_range"), ip.get("type")) != (base, 65536, kind):
                raise RuntimeError("实际Overlay地址／type不符：" + name)
        backend = NlmsAxiDriver(MMIO(BASE_ADDRESS, ADDRESS_RANGE))
        nlms_identity = backend.identify()
        sensors = SensorBus(overlay.axi_iic_0)
        ids = sensors.verify_identities()
        configuration = sensors.configure(fifo_sample_average=1, mpu_sample_rate_hz=50, mpu_dlpf_cfg=4)
        validate_50hz_registers(configuration)
        fifo = AxiFifoLoopback(_resolve_fifo_mmio(overlay, "axi_fifo_mm_s_0"))
        fifo.reset()
        packet = pack_sample(0, 0, 0x12345, -1, 2, -3)
        if fifo.round_trip(packet) != packet:
            raise RuntimeError("原FIFO启动回环失败")
        session.source = CaptureAdapter(sensors, fifo, protocol=settings.protocol)
        session.backend = backend
        session._overlay = overlay
        session._hardware_authorized = True
        session._preflight = dict(**{key: identity[key] for key in IDENTITY_FIELDS},
            nlms_identity=nlms_identity, max30102_id=ids[0], mpu6050_id=ids[1],
            sensor_registers=configuration, fifo_startup_loopback_passed=True,
            limits_sha256=limits.sha256 if limits else None, board_ddr_verified=False)
        session._assess_summary = lambda summary, paths: assess_summary(summary, paths, limits)
        return session
    except BaseException:
        session._release_owner()
        raise


def _rows(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _distribution(values):
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        return None, None
    # NumPy 1.21 用 interpolation；1.22+ 用 method。两者固定为同一线性分位数。
    keyword = "method" if "method" in inspect.signature(np.percentile).parameters else "interpolation"
    return float(np.percentile(values, 99, **{keyword: "linear"})), float(max(values))


def assess_summary(summary, paths, limits):
    """仅在记录线程已关闭后审计；标签只用于协议审计。"""
    from heart_v2.runtime_main_chain import parse_boolean
    raw, results = _rows(paths.raw_csv), _rows(paths.results_csv)
    raw_sequences = [int(row["sequence"]) for row in raw]
    result_sequences = [int(row["sequence"]) for row in results]
    batches = []
    for row in raw:
        if not batches or batches[-1][0] != int(row["batch_id"]):
            batches.append((int(row["batch_id"]), int(row["ppg_read_completed_ns"]), int(row["capture_loop_ns"])))
    gaps = [(right[1] - left[1]) / 1e6 for left, right in zip(batches, batches[1:])]
    read_gap_p99, read_gap_max = _distribution(gaps)
    result_p99, result_max = _distribution([float(row["read_to_result_ns"]) / 1e6 for row in results])
    display = summary.get("display") or {}
    samples = display.get("samples", [])
    display_p99, display_max = _distribution([item["read_to_display_ns"] / 1e6 for item in samples])
    measurements = dict(record_rate_hz=summary["record_rate_hz"], read_gap_p99_ms=read_gap_p99,
        read_gap_max_ms=read_gap_max, capture_loop_overrun_fraction=sum(item[2] > 20_000_000 for item in batches) / len(batches) if batches else None,
        read_to_result_p99_ms=result_p99, read_to_result_max_ms=result_max,
        read_to_display_p99_ms=display_p99, read_to_display_max_ms=display_max)
    forbidden = sum(not parse_boolean(row["output_allowed"], "output_allowed") and bool(row["bpm"]) for row in results)
    snapshot = summary.get("pl_snapshot") or {}
    counts_match = summary["read"] == len(raw) == summary["raw_saved"] == summary["processed"] == len(results) == summary["results_saved"]
    gates = dict(full_duration=summary["stop_reason"] == "duration_complete" and summary["duration_seconds"] == 60.,
        cleanup=summary["cleanup_complete"] and summary["queues_drained"], no_fault=summary["fault"] is None,
        exact_counts=counts_match, sequence_alignment=bool(raw) and raw_sequences == result_sequences == list(range(len(raw))),
        paired=summary["paired_ratio"] is not None and summary["paired_ratio"] >= .995,
        no_queue_full=not any(summary["queue_full"].values()),
        formal_errors_zero=all(summary[key] == 0 for key in ("sensor_errors", "pl_fifo_errors", "max30102_overflow_events",
            "max30102_overflow_count", "timestamp_errors", "timestamp_rejected_samples", "acceleration_invalid_events")),
        known_consumption=not summary["consumed_ppg_unknown"], forbidden_bpm_zero=forbidden == 0,
        real_backend=summary["board_tested"] and summary["backend_source"] == "pl_mmio",
        pl_counts=bool(results) and snapshot.get("accepted") == snapshot.get("emitted") == len(results)
            and snapshot.get("saturated") == 0
            and snapshot.get("clipped") == sum(bool(int(row["pl_status"]) & 4) for row in results)
            and snapshot.get("max_latency_cycles") == max(int(row["pl_latency_cycles"]) for row in results)
            and all(int(row["pl_epoch"]) == snapshot.get("epoch") for row in results),
        pl_public=bool(results) and all(row["backend_source"] == "pl_mmio" and int(row["beta_int"]) == 32212255
            and int(row["pl_sequence"]) == int(row["sequence"]) and 0 < int(row["pl_latency_cycles"]) <= 2048
            and not int(row["pl_status"]) & 8 for row in results),
        display=bool(samples) and display.get("display_errors") == 0 and display.get("disabled") is False
            and all(0 <= item["read_to_display_ns"] <= 1_000_000_000 and not item["historical"] for item in samples))
    if summary["protocol"] == "motion":
        energies = {}
        for phase in ("still_before", "light_motion", "still_after"):
            values = np.array([[float(row[key]) for key in ("ax_g", "ay_g", "az_g")]
                for row in raw if row["phase"] == phase and parse_boolean(row["pair_ok"], "pair_ok")])
            energies[phase] = float(np.mean(np.sum((values - values.mean(axis=0)) ** 2, axis=1))) if len(values) else None
        gates["motion_protocol"] = all(summary["phase_paired_counts"].get(phase, 0) >= 950 for phase in energies)
        gates["motion_energy"] = all(value is not None for value in energies.values()) and energies["light_motion"] > max(energies["still_before"], energies["still_after"])
        summary["protocol_motion_energy_g2"] = energies
    if limits is not None:
        values = limits.document["performance"]
        rate = measurements["record_rate_hz"]
        gates["record_rate_limits"] = rate is not None and values["record_rate_hz_min"] <= rate <= values["record_rate_hz_max"]
        for key in PERFORMANCE_FIELDS[2:]:
            measured = measurements.get(key[:-4])
            gates[key] = measured is not None and measured <= values[key]
    summary.update(measurements=measurements, audit=dict(raw_rows=len(raw), result_rows=len(results),
        forbidden_bpm_rows=forbidden, gates={key: bool(value) for key, value in gates.items()}),
        raw_sha256=_digest(paths.raw_csv), results_sha256=_digest(paths.results_csv), events_sha256=_digest(paths.events_jsonl),
        limits_frozen=summary["mode"] == "acceptance" and limits is not None, limits_sha256=limits.sha256 if limits else None,
        run_acceptance_passed=summary["mode"] == "acceptance" and limits is not None and all(gates.values()))
    # 一个会话永远不代替全部静止／运动／接触／启停板端证据。
    summary["live_50hz_passed"] = summary["board_ddr_verified"] = summary["auto_beta_effect_passed"] = summary["v3a_complete"] = False
    return summary
