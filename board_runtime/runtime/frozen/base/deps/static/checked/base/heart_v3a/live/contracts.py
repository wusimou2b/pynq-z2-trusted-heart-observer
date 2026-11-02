"""实时编排数据契约，不改变冻结的算法参数。"""
from dataclasses import dataclass
import math
from numbers import Integral, Real
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

from heart_axi_capture_50hz import RAW_CSV_FIELDS
from heart_v2.runtime_main_chain import Observation
from heart_v3a.runtime_pl_chain import PlRuntimeFrame

LIVE_RAW_FIELDS = RAW_CSV_FIELDS + (
    "batch_id", "max_write_pointer", "max_read_pointer", "max_available",
    "ppg_read_completed_ns", "mpu_read_completed_ns", "capture_loop_ns",
)


def frozen(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: frozen(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(frozen(item) for item in value)
    return value


def plain(value):
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError(name + "必须为有限数")
    return float(value)


@dataclass(frozen=True)
class LiveSettings:
    mode: str = "baseline"
    protocol: str = "static"
    duration_seconds: float = 60.0

    def __post_init__(self):
        duration = finite(self.duration_seconds, "持续时间")
        if self.mode not in ("baseline", "acceptance") or self.protocol not in ("static", "motion", "contact"):
            raise ValueError("模式／协议不合法")
        if not 0 < duration <= 60 or self.protocol != "static" and duration != 60:
            raise ValueError("静止须0–60秒，轻晃／接触协议固定60秒")
        if self.mode == "baseline" and self.protocol != "static":
            raise ValueError("基准只允许静止协议")


@dataclass(frozen=True)
class LiveFault:
    stage: str
    reason: str
    sequence: int | None
    occurred_ns: int
    details: Mapping[str, object]

    def __post_init__(self):
        object.__setattr__(self, "details", frozen(self.details))


@dataclass(frozen=True)
class LiveRecord:
    raw: Mapping[str, object]
    read_completed_ns: int

    def __post_init__(self):
        row = dict(self.raw)
        if any(name not in row for name in LIVE_RAW_FIELDS):
            raise ValueError("原始记录字段不完整")
        if isinstance(row["sequence"], bool) or not isinstance(row["sequence"], Integral) or row["sequence"] < 0:
            raise ValueError("序号必须为非负整数")
        finite(row["ir_raw"], "PPG")
        for name in ("pair_ok", "accel_valid"):
            if type(row[name]) is not bool:
                raise ValueError(name + "必须为bool")
        if row["pl_fifo_ok"] != "" and type(row["pl_fifo_ok"]) is not bool:
            raise ValueError("pl_fifo_ok必须为bool或未尝试的空值")
        if row["time_s"] == "":
            if not row["error"]:
                raise ValueError("缺失时间只能出现在已记录的终端故障中")
        else:
            finite(row["time_s"], "相对时间")
        if row["pair_ok"]:
            if not row["accel_valid"]:
                raise ValueError("配对记录必须有有效加速度")
            for name in ("ax_g", "ay_g", "az_g"):
                finite(row[name], name)
        if isinstance(self.read_completed_ns, bool) or not isinstance(self.read_completed_ns, Integral) or self.read_completed_ns < 0:
            raise ValueError("读取完成时间必须为非负整数纳秒")
        object.__setattr__(self, "raw", frozen(row))

    def to_observation(self) -> Observation:
        row = self.raw
        if row["time_s"] == "" or row["sequence"] > 0xFFFFFFFF:
            raise ValueError("终端时间／序号故障记录不能送入算法")
        axes = tuple(float(row[name]) for name in ("ax_g", "ay_g", "az_g")) if row["pair_ok"] else (math.nan,) * 3
        return Observation(int(row["sequence"]), float(row["time_s"]), float(row["ir_raw"]),
            axes, row["pair_ok"], contact_ok=None, reset=False,
            pl_fifo_ok=row["pl_fifo_ok"] is not False, accel_valid=row["accel_valid"], error=str(row["error"]))


@dataclass(frozen=True)
class LiveBatch:
    batch_id: int
    records: tuple[LiveRecord, ...]
    queued_ns: int
    fault: LiveFault | None = None

    def __post_init__(self):
        if len(self.records) > 32:
            raise ValueError("PPG批次超过32条")
        object.__setattr__(self, "records", tuple(self.records))


@dataclass(frozen=True)
class SavedRecord:
    record: LiveRecord
    raw_saved_ns: int
    process_enqueued_ns: int


@dataclass(frozen=True)
class ProcessedRecord:
    saved: SavedRecord
    runtime: PlRuntimeFrame
    processing_started_ns: int
    processing_finished_ns: int
    pl_call_ns: int
    result_enqueued_ns: int


@dataclass(frozen=True)
class LiveSnapshot:
    state: str
    fault: LiveFault | None
    latest: ProcessedRecord | None
    history: tuple[ProcessedRecord, ...]
    counts: Mapping[str, object]

    def __post_init__(self):
        object.__setattr__(self, "history", tuple(self.history))
        object.__setattr__(self, "counts", frozen(self.counts))


@dataclass(frozen=True)
class LivePaths:
    directory: Path
    raw_csv: Path
    results_csv: Path
    events_jsonl: Path
    summary_json: Path
