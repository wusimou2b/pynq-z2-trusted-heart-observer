"""原始flush是处理许可屏障；单一记录所有者管理实际文件。"""
import csv
from dataclasses import asdict, fields
import json
from pathlib import Path
import time

from heart_v2.runtime_main_chain import RuntimeFrame
from heart_v3a.runtime_pl_chain import PlRuntimeFrame
from .contracts import LIVE_RAW_FIELDS, LivePaths, SavedRecord, plain

RESULT_FIELDS = tuple(field.name for field in fields(RuntimeFrame)) + tuple(
    field.name for field in fields(PlRuntimeFrame) if field.name != "frame") + (
    "ppg_read_completed_ns", "raw_saved_ns", "process_enqueued_ns", "processing_started_ns",
    "processing_finished_ns", "pl_call_ns", "result_enqueued_ns", "processing_queue_wait_ns",
    "result_queue_wait_ns", "read_to_result_ns", "ps_processing_ns",
)


class LiveJournal:
    def __init__(self, directory, *, clock=time):
        root = Path(directory).resolve()
        self.paths = LivePaths(root, root / "raw.csv", root / "results.csv", root / "events.jsonl", root / "summary.json")
        self.clock = clock
        self._opened = False
        self._closed = False
        self._raw_stream = self._result_stream = self._event_stream = None
        self._counts = dict(raw_attempted=0, raw_saved=0, results_attempted=0, results_saved=0, events_saved=0)

    def open(self):
        if self._opened:
            raise RuntimeError("记录器不能重复打开")
        self.paths.directory.mkdir(parents=True, exist_ok=False)
        self._opened = True
        try:
            self._raw_stream = self.paths.raw_csv.open("x", encoding="utf-8", newline="")
            self._result_stream = self.paths.results_csv.open("x", encoding="utf-8", newline="")
            self._event_stream = self.paths.events_jsonl.open("x", encoding="utf-8", newline="")
            self._raw_writer = csv.DictWriter(self._raw_stream, fieldnames=LIVE_RAW_FIELDS, lineterminator="\n")
            self._result_writer = csv.DictWriter(self._result_stream, fieldnames=RESULT_FIELDS, lineterminator="\n")
            self._raw_writer.writeheader()
            self._result_writer.writeheader()
            self._raw_stream.flush()
            self._result_stream.flush()
        except Exception:
            self.close()
            raise
        return self.paths

    def save_raw(self, batch):
        started = self.clock.monotonic_ns()
        self._counts["raw_attempted"] += len(batch.records)
        self._raw_writer.writerows({name: record.raw[name] for name in LIVE_RAW_FIELDS} for record in batch.records)
        self._raw_stream.flush()
        saved_ns = self.clock.monotonic_ns()
        self._counts["raw_saved"] += len(batch.records)
        self.save_event(dict(stage="raw_flushed", batch_id=batch.batch_id, samples=len(batch.records),
            raw_saved_ns=saved_ns, raw_queue_wait_ns=started - batch.queued_ns,
            raw_write_ns=saved_ns - started))
        return tuple(SavedRecord(record, saved_ns, 0) for record in batch.records)

    def save_result(self, result):
        runtime = asdict(result.runtime)
        row = runtime.pop("frame")
        row.update(runtime)
        saved = result.saved
        row.update(ppg_read_completed_ns=saved.record.read_completed_ns, raw_saved_ns=saved.raw_saved_ns,
            process_enqueued_ns=saved.process_enqueued_ns, processing_started_ns=result.processing_started_ns,
            processing_finished_ns=result.processing_finished_ns, pl_call_ns=result.pl_call_ns,
            result_enqueued_ns=result.result_enqueued_ns,
            processing_queue_wait_ns=result.processing_started_ns - saved.process_enqueued_ns,
            result_queue_wait_ns=self.clock.monotonic_ns() - result.result_enqueued_ns,
            read_to_result_ns=result.processing_finished_ns - saved.record.read_completed_ns,
            ps_processing_ns=result.processing_finished_ns - result.processing_started_ns - result.pl_call_ns)
        self._counts["results_attempted"] += 1
        self._result_writer.writerow(row)
        self._result_stream.flush()
        self._counts["results_saved"] += 1

    def save_event(self, event):
        self._event_stream.write(json.dumps(plain(event), ensure_ascii=False, allow_nan=False) + "\n")
        self._event_stream.flush()
        self._counts["events_saved"] += 1

    def counts(self):
        return dict(self._counts)

    def close(self):
        if self._closed:
            return
        error = None
        for stream in (self._raw_stream, self._result_stream, self._event_stream):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except Exception as exc:
                    error = error or exc
        self._closed = all(stream is None or stream.closed for stream in
            (self._raw_stream, self._result_stream, self._event_stream))
        if error:
            raise error

    def write_summary(self, summary):
        if not self._closed:
            raise RuntimeError("工作文件尚未关闭，不能交接最终汇总")
        with self.paths.summary_json.open("x", encoding="utf-8") as stream:
            json.dump(plain(summary), stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
