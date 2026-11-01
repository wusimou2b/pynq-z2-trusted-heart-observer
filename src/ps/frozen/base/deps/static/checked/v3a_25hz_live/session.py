"""Independent 25 Hz adapter atop the frozen raw50 lifecycle and queues."""
from dataclasses import asdict, replace
from queue import Empty
import time

from heart_v3a.live.session import LiveSession, MeasuredBackend
from heart_v3a.live.isolated import IsolatedLiveSession
from v3a_rate25.frontend import RawFrontend
from .bridge import ProcessChain25
from .contracts import ProcessedSlot
from .journal import SlotJournal
from .safety import RawSafety


class _SupervisedSource:
    def __init__(self, source, session):
        self.source, self.session = source, session

    def begin(self):
        return self.source.begin()

    def read_batch(self):
        batch = self.source.read_batch()
        for record in batch.records:
            try:
                self.session._safety.observe(record.to_observation(), record.read_completed_ns)
            except Exception as exc:
                # Still return the complete consumed batch to the raw journal.
                self.session._fail('raw_safety', str(exc), record.raw['sequence'])
                break
        return batch

    def diagnostic_snapshot(self):
        self.source._capture_stopped = True
        return self.source.diagnostic_snapshot()


class LiveSession25(IsolatedLiveSession):
    """No board loader here. Source/parent backend must be provided explicitly."""
    def __init__(self, source, backend, output_dir, settings, *, clock=time):
        super().__init__(source, backend, output_dir, settings, clock=clock)
        self._safety = RawSafety()
        self._frontend = RawFrontend()
        self._journal = SlotJournal(self.output_dir, clock=clock)
        self.source = _SupervisedSource(source, self)

    def start(self):
        with self._lock:
            if self._started_once or self._state != 'created':
                raise RuntimeError('会话只能启动一次')
            self._claim_owner()
        try:
            self._process_chain = ProcessChain25(self.backend.source)
        except BaseException as exc:
            self._fail('process_preflight', str(exc))
            self.stop()
            raise
        try:
            return LiveSession.start(self)
        except BaseException as exc:
            self._fail('startup', str(exc))
            self.stop()
            raise

    def _guard_result(self, result, now_ns):
        frame = self._safety.guard(result.slot, result.runtime.frame,
                                   result.saved.record.read_completed_ns, now_ns=now_ns)
        if self._state != 'running' or self._fault is not None:
            frame = replace(frame, bpm=None, output_allowed=False, reason_cn='会话非运行态／故障阻断')
        return replace(result, runtime=replace(result.runtime, frame=frame))

    def snapshot(self, *, now_ns=None):
        with self._lock:
            snapshot = super().snapshot()
            latest = snapshot.latest
            if latest is not None:
                latest = self._guard_result(latest, self.clock.monotonic_ns() if now_ns is None else now_ns)
            return replace(snapshot, latest=latest, counts={**snapshot.counts,
                           'raw_safety': asdict(self._safety.snapshot())})

    def _process_loop(self):
        measured = None
        pending = []
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
                # The frozen journal only enqueues after raw flush succeeds.
                with self._lock:
                    slot = self._frontend.push(saved.record.to_observation())
                pending.append(saved)
                if slot is None:
                    continue
                pair, pending = tuple(pending), []
                if len(pair) != 2 or tuple(s.record.raw['sequence'] for s in pair) != slot.source_sequences:
                    raise RuntimeError('25Hz原始双点来源不符')
                runtime = chain.step(slot)
                finished = self.clock.monotonic_ns()
                result = ProcessedSlot(pair, slot, runtime, started, finished,
                                       measured.last_call_ns, self.clock.monotonic_ns())
                with self._lock:
                    guarded = self._guard_result(result, finished).runtime.frame
                    result = replace(result, publication_allowed=guarded.output_allowed,
                                     publication_bpm=guarded.bpm, publication_reason=guarded.reason_cn)
                    self._counts['processed'] += 1
                    self._latest = result
                    self._history.append(result)
                self._offer_result(result)
        except Exception as exc:
            self._fail('processing', str(exc))
        finally:
            self._processor_ready.set()
            if measured is not None and (self._fault is None or self._fault.stage != 'processing'):
                try:
                    self._pl_snapshot = measured.snapshot()
                except Exception as exc:
                    self._pl_snapshot_error = str(exc)
                    self._fail('pl_final_snapshot', str(exc))
            else:
                self._pl_snapshot_error = '后端故障，未重试快照／未reset清计数'
            try:
                self._close_processing_chain()
            except Exception as exc:
                self._fail('processing_cleanup', str(exc))
            self._processor_done.set()

    def _make_summary(self, cleanup_complete, display_metrics=None):
        with self._lock:
            result = super()._make_summary(cleanup_complete, display_metrics)
            audit = self._frontend.audit()
            unadapted = result['raw_saved']-audit['raw_received']
            unfinished_slots = audit['slots_emitted']-result['processed']
            unprocessed = result['raw_saved']-2*result['processed']
            result.update(schema='v3a_raw50_process25_live_v1', raw_hz=50, processing_hz=25,
                peak_version='raw50_process25_fractional_peaks_v2', frontend=audit,
                raw_safety=asdict(self._safety.snapshot()), unadapted_saved_raw=unadapted,
                formed_unprocessed_slots=unfinished_slots, unprocessed_raw=unprocessed,
                consumed_raw_by_results=2*result['processed'],
                count_identity=(audit['count_identity'] and min(unadapted, unfinished_slots, unprocessed) >= 0
                    and unprocessed == unadapted+audit['pending_raw']+2*unfinished_slots),
                processing_queue_unit='raw_records', processing_queue_capacity=250,
                live_25hz_passed=False, live_50hz_passed=False,
                display_age_guard_ns=1_000_000_000, display_age_limit_frozen=False)
            return result
