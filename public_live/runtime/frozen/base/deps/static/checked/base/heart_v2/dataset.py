"""离线算法竞技场的数据模型与加载器。"""

import hashlib
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ("sequence", "ir_raw", "ax_g", "ay_g", "az_g")


class DatasetError(ValueError):
    """采集文件无法表示为合法数据集时抛出此异常。"""


@dataclass(frozen=True)
class ArenaSegment:
    index: int
    start: int
    stop: int
    phase: str


@dataclass(frozen=True)
class ArenaDataset:
    source_path: str
    source_sha256: str
    source_schema: str
    sample_rate_hz: float
    columns: Mapping[str, np.ndarray]
    segments: tuple[ArenaSegment, ...]


def load_capture(
    path: str | Path,
    expected_rate_hz: float | None = None,
    gap_factor: float = 3.0,
) -> ArenaDataset:
    """加载并校验采集 CSV，输出独立数组，不保留 pandas 对象。"""
    source_path = Path(path)
    source_bytes = source_path.read_bytes()
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()

    try:
        frame = pd.read_csv(BytesIO(source_bytes))
    except Exception as exc:
        raise DatasetError(f"Could not parse capture {source_path}: {exc}") from exc

    missing = [name for name in REQUIRED_COLUMNS if name not in frame.columns]
    if missing:
        raise DatasetError(f"Missing required columns: {', '.join(missing)}")

    time_column = "timestamp_us" if "timestamp_us" in frame.columns else "time_s"
    if time_column not in frame.columns:
        raise DatasetError("Capture requires timestamp_us or time_s")

    numeric_columns: dict[str, np.ndarray] = {}
    explicitly_unpaired = np.zeros(len(frame), dtype=bool)
    if 'pair_ok' in frame.columns:
        explicitly_unpaired = frame['pair_ok'].map(
            lambda value: str(value).strip().lower() in {'false', '0', '0.0'}
        ).to_numpy(dtype=bool)
    for name in (*REQUIRED_COLUMNS, time_column):
        numeric = pd.to_numeric(frame[name], errors="coerce").to_numpy(dtype=float)
        invalid_values = ~np.isfinite(numeric)
        if name in {'ax_g', 'ay_g', 'az_g'}:
            # 明确未配对的空加速度保留为 NaN；有效样本、非法文本及无穷值仍拒绝。
            allowed_missing = explicitly_unpaired & frame[name].isna().to_numpy() & np.isnan(numeric)
            invalid_values &= ~allowed_missing
        invalid = np.flatnonzero(invalid_values)
        if invalid.size:
            source_row = int(invalid[0]) + 2
            raise DatasetError(
                f"Column {name} has a nonnumeric or nonfinite value at source row {source_row}"
            )
        numeric_columns[name] = numeric

    time_values = numeric_columns[time_column]
    if time_column == "timestamp_us":
        time_seconds = time_values / 1_000_000.0
    else:
        time_seconds = time_values

    intervals = np.diff(time_seconds)
    non_increasing = np.flatnonzero(intervals <= 0.0)
    if non_increasing.size:
        source_row = int(non_increasing[0]) + 3
        raise DatasetError(f"Time is non-increasing at source row {source_row}")

    if expected_rate_hz is None:
        if intervals.size == 0:
            raise DatasetError("Cannot derive sample rate from fewer than two rows")
        sample_rate_hz = 1.0 / float(np.median(intervals[intervals > 0.0]))
    else:
        sample_rate_hz = float(expected_rate_hz)
    if not np.isfinite(sample_rate_hz) or sample_rate_hz <= 0.0:
        raise DatasetError("The sample rate must be positive and finite")
    if not np.isfinite(gap_factor) or gap_factor <= 0.0:
        raise DatasetError("The gap factor must be positive and finite")

    columns: dict[str, np.ndarray] = {}
    for name in frame.columns:
        if name in numeric_columns:
            values = numeric_columns[name].copy()
        else:
            values = frame[name].to_numpy(copy=True)
        columns[name] = values

    lengths = {len(values) for values in columns.values()}
    if lengths != {len(frame)}:
        raise DatasetError("Capture columns have inconsistent lengths")

    if "phase" in columns:
        phases = frame["phase"].fillna("unlabeled").astype(str).to_numpy(copy=True)
        columns["phase"] = phases.copy()
        source_schema = "labeled_50hz"
    else:
        phases = np.full(len(frame), "unlabeled", dtype=object)
        contact_fields = {
            name
            for name in columns
            if name in {"baseline_ir", "pulse_amplitude"}
            or name == "contact_ok"
            or name.startswith("contact_")
            or name.startswith("quality_")
        }
        source_schema = "v1_contact" if contact_fields else "v1_legacy"

    boundaries = [0]
    maximum_interval = gap_factor / sample_rate_hz
    for row in range(1, len(frame)):
        if intervals[row - 1] > maximum_interval or phases[row] != phases[row - 1]:
            boundaries.append(row)
    boundaries.append(len(frame))
    segments = tuple(
        ArenaSegment(
            index=index,
            start=start,
            stop=stop,
            phase=str(phases[start]),
        )
        for index, (start, stop) in enumerate(zip(boundaries, boundaries[1:]))
        if start < stop
    )

    return ArenaDataset(
        source_path=str(source_path),
        source_sha256=source_sha256,
        source_schema=source_schema,
        sample_rate_hz=sample_rate_hz,
        columns=columns,
        segments=segments,
    )
