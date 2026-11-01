"""有界实时会话；故障锁定，不自动重试或切换后端。"""
from collections import deque
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from queue import Empty, Full, Queue
import threading
import time

from .processing import ReusingRuntimePlMainChain as RuntimePlMainChain
from .contracts import LiveFault, LiveSnapshot, ProcessedRecord, plain
from .journal import LiveJournal

_OWNERSHIP_LOCK = threading.Lock()
_ACTIVE_SESSION = None


class MeasuredBackend:
    def __init__(self, backend, *, clock=time):
        self.backend, self.source, self.clock = backend, backend.source, clock
        self.last_call_ns = 0

    def reset(self):
        return self.backend.reset()

    def transact(self, packet):
        started = self.clock.monotonic_ns()
        try:
            return self.backend.transact(packet)
        finally:
            self.last_call_ns = self.clock.monotonic_ns() - started

    def snapshot(self):
        method = getattr(self.backend, "snapshot", None)
        return method() if method else None


class LiveSession:
    def __init__(self, source, backend, output_dir, settings, *, clock=time):
        self.source, self.backend, self.settings, self.clock = source, backend, settings, clock
        self.output_dir = Path(output_dir).resolve()
        self._journal = LiveJournal(self.output_dir, clock=clock)
        self._lock = threading.RLock()
        self._stop_lock = threading.Lock()
        self._state = "created"
        self._started_once = False
        self._closed = False
        self._fault = None
        self._stop_reason = ""
        self._threads = []
        self._finalizer = None
        self._summary = {}
        self._finished_summary = None
        self._paths = None
        self._terminal_batch = None
        self._raw_queue, self._processing_queue, self._result_queue = Queue(8), Queue(250), Queue(250)
        self._stop_requested = threading.Event()
        self._producer_closed = threading.Event()
        self._raw_drained = threading.Event()
        self._processor_done = threading.Event()
        self._processor_ready = threading.Event()
        self._journal_ready = threading.Event()
        self._capture_ready = threading.Event()
        self._latest = None
        self._history = deque(maxlen=500)
        self._counts = dict(read=0, process_enqueued=0, processed=0, paired=0, unpaired=0,
            batches=0, max_fifo_batch=0, capture_loop_overruns=0, sensor_errors=0, pl_fifo_errors=0,
            max30102_overflow_events=0, max30102_overflow_count=0, timestamp_errors=0,
            timestamp_rejected_samples=0, acceleration_invalid_events=0, consumed_ppg_unknown=False)
        self._phase_counts = {}
        self._queue_high = dict(raw=0, processing=0, results=0)
        self._queue_full = dict(raw=0, processing=0, results=0)
        self._startup = {}
        self._pl_snapshot = None
        self._pl_snapshot_error = ""
        self._hardware_authorized = False
        self._board_lease = None
        self._preflight = {}
        self._assess_summary = None
        self._elapsed_seconds = 0.

    @property
    def paths(self):
        return self._paths

    @property
    def summary(self):
        with self._lock:
            return deepcopy(self._summary)

    def _claim_owner(self):
        global _ACTIVE_SESSION
        with _OWNERSHIP_LOCK:
            if _ACTIVE_SESSION is not None and _ACTIVE_SESSION is not self:
                raise RuntimeError("已有会话持有硬件所有权")
            _ACTIVE_SESSION = self

    def _release_owner(self):
        global _ACTIVE_SESSION
        with _OWNERSHIP_LOCK:
            if _ACTIVE_SESSION is self:
                if self._board_lease is not None:
                    self._board_lease.release()
                _ACTIVE_SESSION = None

    def _fail(self, stage, reason, sequence=None, details=None):
        with self._lock:
            if self._fault is None:
                self._fault = LiveFault(stage, reason, sequence, self.clock.monotonic_ns(), details or {})
            if self._state != "shutdown_incomplete":
                self._state = "faulted"
            self._stop_requested.set()

    def _request_stop(self, reason):
        with self._lock:
            self._stop_reason = self._stop_reason or reason
            if self._fault is None and self._state not in ("stopped", "shutdown_incomplete"):
                self._state = "stopping"
            self._stop_requested.set()

    def _offer(self, queue, payload, name):
        try:
            queue.put_nowait(payload)
        except Full:
            with self._lock:
                self._queue_full[name] += 1
            self._fail(name + "_queue", name + "有界队列已满")
            return False
        with self._lock:
            self._queue_high[name] = max(self._queue_high[name], queue.qsize())
        return True

    def _offer_processing(self, saved):
        if not self._offer(self._processing_queue, saved, "processing"):
            return False
        with self._lock:
            self._counts["process_enqueued"] += 1
        return True

    def _offer_result(self, result):
        return self._offer(self._result_queue, result, "results")

    def start(self):
        with self._lock:
            if self._started_once or self._state != "created":
                raise RuntimeError("会话只能启动一次")
            self._claim_owner()
            self._started_once = True
            self._state = "preflight"
        deadline = time.monotonic() + 3.
        try:
            journal = threading.Thread(target=self._record_loop, name="v3a-live-journal", daemon=True)
            processor = threading.Thread(target=self._process_loop, name="v3a-live-processor", daemon=True)
            self._threads.extend((journal, processor))
            journal.start()
            processor.start()
            for event in (self._journal_ready, self._processor_ready):
                if not event.wait(max(0., deadline - time.monotonic())):
                    raise TimeoutError("实时启动等待超过工程预算")
            if self._fault is not None:
                raise RuntimeError("实时初始化失败：" + self._fault.reason)
            producer = threading.Thread(target=self._capture_loop, name="v3a-live-producer", daemon=True)
            self._threads.append(producer)
            producer.start()
            if not self._capture_ready.wait(max(0., deadline - time.monotonic())):
                raise TimeoutError("正式采集起点尚未就绪")
        except BaseException as exc:
            self._fail("startup", str(exc))
            if len(self._threads) < 3:
                self._producer_closed.set()
            self.stop()
            raise
        return self

    def _capture_loop(self):
        started_ns = None
        try:
            self._startup = self.source.begin()
            started_ns = self._startup["started_ns"]
            with self._lock:
                if self._fault is None and not self._stop_requested.is_set():
                    self._state = "running"
            self._capture_ready.set()
            while not self._stop_requested.is_set():
                if (self.clock.monotonic_ns() - started_ns) / 1e9 >= self.settings.duration_seconds:
                    self._request_stop("duration_complete")
                    break
                try:
                    batch = self.source.read_batch()
                except StopIteration:
                    self._request_stop("finite_input_complete")
                    break
                with self._lock:
                    size = len(batch.records)
                    self._counts["read"] += size
                    self._counts["batches"] += 1
                    self._counts["max_fifo_batch"] = max(size, self._counts["max_fifo_batch"])
                    for record in batch.records:
                        paired = record.raw["pair_ok"]
                        self._counts["paired" if paired else "unpaired"] += 1
                        phase = str(record.raw["phase"])
                        self._phase_counts[phase] = self._phase_counts.get(phase, 0) + int(paired)
                    if batch.records:
                        first = batch.records[0].raw
                        self._counts["capture_loop_overruns"] += int(first["capture_loop_ns"] > 20_000_000)
                        self._counts["max30102_overflow_events"] += int(first["max30102_overflow"] > 0)
                        self._counts["max30102_overflow_count"] += first["max30102_overflow"]
                if not self._offer(self._raw_queue, batch, "raw"):
                    self._terminal_batch = batch
                    break
                if batch.fault:
                    fault = batch.fault
                    with self._lock:
                        self._counts["sensor_errors"] += int(fault.reason == "sensor_read_exception")
                        self._counts["acceleration_invalid_events"] += int(fault.stage == "mpu_acceleration_read")
                        self._counts["pl_fifo_errors"] += int(fault.stage == "axi_fifo_loopback")
                        self._counts["timestamp_errors"] += int(fault.stage == "timestamp_reconstruction")
                        self._counts["timestamp_rejected_samples"] += size if fault.stage == "timestamp_reconstruction" else 0
                        self._counts["consumed_ppg_unknown"] |= bool(fault.details.get("consumed_ppg_unknown"))
                    self._fail(fault.stage, fault.reason, fault.sequence, plain(fault.details))
                    break
        except Exception as exc:
            self._fail("capture", str(exc), details=dict(consumed_ppg_unknown=True))
            with self._lock:
                self._counts["sensor_errors"] += 1
                self._counts["consumed_ppg_unknown"] = True
        finally:
            if started_ns is not None:
                self._elapsed_seconds = (self.clock.monotonic_ns() - started_ns) / 1e9
            self._producer_closed.set()
            self._capture_ready.set()
            self._request_stop("capture_finished")

    def _create_processing_chain(self, measured):
        return RuntimePlMainChain(measured)

    def _close_processing_chain(self):
        pass

    def _process_loop(self):
        measured = None
        try:
            measured = MeasuredBackend(self.backend, clock=self.clock)
            chain = self._create_processing_chain(measured)
            chain.reset()
            self._processor_ready.set()
            while not (self._raw_drained.is_set() and self._processing_queue.empty()):
                try:
                    saved = self._processing_queue.get(timeout=.01)
                except Empty:
                    continue
                if self._fault is not None:
                    continue
                started = self.clock.monotonic_ns()
                runtime = chain.step(saved.record.to_observation(), beta_int=32212255, update_enabled=True, bypass=False)
                finished = self.clock.monotonic_ns()
                if runtime.pl_sequence is None or runtime.pl_epoch is None or runtime.pl_status is None:
                    self._fail("nlms", "本拍没有可核对的PL公开结果", saved.record.raw["sequence"])
                    continue
                result = ProcessedRecord(saved, runtime, started, finished, measured.last_call_ns, self.clock.monotonic_ns())
                with self._lock:
                    self._counts["processed"] += 1
                    self._latest = result
                    self._history.append(result)
                self._offer_result(result)
        except Exception as exc:
            self._fail("processing", str(exc))
        finally:
            self._processor_ready.set()
            if measured is not None and (self._fault is None or self._fault.stage not in ("nlms", "processing")):
                try:
                    self._pl_snapshot = measured.snapshot()
                except Exception as exc:
                    self._pl_snapshot_error = str(exc)
                    self._fail("pl_final_snapshot", str(exc))
            else:
                self._pl_snapshot_error = "后端故障，未重试最终快照／未reset擦除计数"
            try:
                self._close_processing_chain()
            except Exception as exc:
                self._fail("processing_cleanup", str(exc))
            self._processor_done.set()

    def _record_loop(self):
        try:
            self._paths = self._journal.open()
            self._journal_ready.set()
            raw_done = False
            while not (raw_done and self._processor_done.is_set() and self._result_queue.empty()):
                if not raw_done:
                    try:
                        batch = self._raw_queue.get(timeout=.01)
                    except Empty:
                        batch = None
                        if self._producer_closed.is_set():
                            batch, self._terminal_batch = self._terminal_batch, None
                            if batch is None:
                                raw_done = True
                                self._raw_drained.set()
                    if batch is not None:
                        saved_records = self._journal.save_raw(batch)
                        for saved in saved_records:
                            if self._fault is not None:
                                break
                            if not self._offer_processing(replace(saved, process_enqueued_ns=self.clock.monotonic_ns())):
                                break
                for index in range(32):
                    try:
                        # 原始输入结束后无采集需要兼顾；等待结果，避免空转争抢GIL。
                        result = (self._result_queue.get(timeout=.01) if raw_done and index == 0
                                  else self._result_queue.get_nowait())
                    except Empty:
                        break
                    self._journal.save_result(result)
            if self._fault:
                fault = self._fault
                self._journal.save_event(dict(stage=fault.stage, reason=fault.reason, sequence=fault.sequence,
                    occurred_ns=fault.occurred_ns, details=plain(fault.details)))
        except Exception as exc:
            self._fail("journal", str(exc))
        finally:
            self._raw_drained.set()
            self._journal_ready.set()
            try:
                self._journal.close()
            except Exception as exc:
                self._fail("journal_close", str(exc))

    def snapshot(self):
        with self._lock:
            counts = {**self._counts, **self._journal.counts()}
            return LiveSnapshot(self._state, self._fault, self._latest, tuple(self._history), counts)

    def _make_summary(self, cleanup_complete, display_metrics=None):
        with self._lock:
            result = dict(self._counts)
            result.update(self._journal.counts())
            fault = self._fault
            result.update(state=self._state, stop_reason=self._stop_reason,
                fault=dict(stage=fault.stage, reason=fault.reason, sequence=fault.sequence,
                    occurred_ns=fault.occurred_ns, details=plain(fault.details)) if fault else None,
                cleanup_complete=cleanup_complete, backend_source=getattr(self.backend, "source", "unavailable"),
                board_tested=self._hardware_authorized, live_50hz_passed=False, auto_beta_effect_passed=False,
                board_ddr_verified=False, v3a_complete=False, limits_frozen=False, run_acceptance_passed=False,
                protocol=self.settings.protocol, mode=self.settings.mode, duration_seconds=self.settings.duration_seconds,
                elapsed_seconds=self._elapsed_seconds, summary_written=False,
                paired_ratio=result["paired"] / result["read"] if result["read"] else None,
                record_rate_hz=result["read"] / self._elapsed_seconds if self._elapsed_seconds > 0 else None,
                phase_paired_counts=dict(self._phase_counts), queue_high_water=dict(self._queue_high),
                queue_full=dict(self._queue_full), queues_drained=all(q.empty() for q in
                    (self._raw_queue, self._processing_queue, self._result_queue)),
                startup=dict(self._startup), pl_snapshot_available=self._pl_snapshot is not None,
                pl_snapshot=self._pl_snapshot, pl_snapshot_error=self._pl_snapshot_error,
                preflight=deepcopy(self._preflight), display_measured=display_metrics is not None,
                display=plain(display_metrics) if display_metrics is not None else None)
            result.update(unsaved_raw=result["read"] - result["raw_saved"],
                unprocessed_raw=result["raw_saved"] - result["processed"],
                unsaved_results=result["processed"] - result["results_saved"])
            return result

    def _finish(self, display_metrics):
        try:
            if self._paths is not None and self._fault is not None:
                self.source._capture_stopped = True
                diagnostic = self.source.diagnostic_snapshot()
            else:
                diagnostic = dict(available=False, reason_cn="正常停止未追加诊断")
            with self._lock:
                summary = self._make_summary(True, display_metrics)
                summary["state"] = "faulted" if self._fault else "stopped"
                summary["diagnostic"] = diagnostic
            if self._assess_summary is not None and self._paths is not None:
                summary = self._assess_summary(summary, self._paths)
            if self._paths is not None:
                summary["summary_written"] = True
                self._journal.write_summary(summary)
            with self._lock:
                self._finished_summary = summary
        except Exception as exc:
            self._fail("finalization", str(exc))
            with self._lock:
                self._finished_summary = self._make_summary(True, display_metrics)
                self._finished_summary["state"] = "faulted"

    def stop(self, *, display_metrics=None):
        deadline = time.monotonic() + 3.
        if not self._stop_lock.acquire(timeout=3.):
            result = self._make_summary(False, display_metrics)
            result["state"] = "shutdown_incomplete"
            return result
        try:
            if self._closed:
                return self.summary
            self._request_stop("manual_stop")
            for worker in self._threads:
                if worker.ident is not None:
                    worker.join(max(0., deadline - time.monotonic()))
            if any(worker.is_alive() for worker in self._threads):
                with self._lock:
                    self._state = "shutdown_incomplete"
                    self._summary = self._make_summary(False, display_metrics)
                return self.summary
            if self._finalizer is None:
                self._finalizer = threading.Thread(target=self._finish, args=(display_metrics,),
                    name="v3a-live-finalizer", daemon=True)
                self._finalizer.start()
            self._finalizer.join(max(0., deadline - time.monotonic()))
            if self._finalizer.is_alive() or self._paths is not None and not self._journal._closed:
                with self._lock:
                    self._state = "shutdown_incomplete"
                    self._summary = self._make_summary(False, display_metrics)
                return self.summary
            self._closed = True
            with self._lock:
                self._summary = self._finished_summary
                self._state = self._summary["state"]
            self._release_owner()
            return self.summary
        finally:
            self._stop_lock.release()
