"""One-to-one session, preserving frozen queue, flush, stop and ownership lifecycle."""
from dataclasses import asdict, replace
from queue import Empty
import time
from heart_v3a.live.session import LiveSession, MeasuredBackend
from heart_v3a.live.isolated import IsolatedLiveSession
from v3a_25hz_live.session import LiveSession25, _SupervisedSource
from v3a_25hz_live.contracts import ProcessedSlot
from .frontend import Frontend25
from .safety import Safety25
from .bridge import Bridge25
from .policy import VERSION, PERIOD_US


class SupervisedSource25(_SupervisedSource):
    def read_batch(self):
        batch=super().read_batch()
        if batch.records:
            # The frozen lifecycle retains its internal 20ms counter; public
            # snapshots and summaries use this independently measured 40ms one.
            with self.session._lock:
                self.session._overruns25+=int(batch.records[0].raw['capture_loop_ns']>PERIOD_US*1000)
        return batch


class Session25(LiveSession25):
    def __init__(self,source,backend,output_dir,settings,*,clock=time):
        super().__init__(source,backend,output_dir,settings,clock=clock)
        self._safety=Safety25(); self._frontend=Frontend25(); self._overruns25=0
        self.source=SupervisedSource25(source,self)

    def start(self):
        with self._lock:
            if self._started_once or self._state!='created': raise RuntimeError('会话只能启动一次')
            self._claim_owner()
        try: self._process_chain=Bridge25(self.backend.source)
        except BaseException as exc:
            self._fail('process_preflight',str(exc)); self.stop(); raise
        try: return LiveSession.start(self)
        except BaseException as exc:
            self._fail('startup',str(exc)); self.stop(); raise

    def snapshot(self,*,now_ns=None):
        with self._lock:
            snapshot=super().snapshot(now_ns=now_ns)
            return replace(snapshot,counts={**snapshot.counts,'capture_loop_overruns':self._overruns25})

    def _process_loop(self):
        measured=None
        try:
            measured=MeasuredBackend(self.backend,clock=self.clock)
            chain=self._create_processing_chain(measured); chain.reset(); self._processor_ready.set()
            while not (self._raw_drained.is_set() and self._processing_queue.empty()):
                try: saved=self._processing_queue.get(timeout=.01)
                except Empty: continue
                if self._fault is not None: continue
                started=self.clock.monotonic_ns()
                with self._lock: slot=self._frontend.push(saved.record.to_observation())
                if slot.source_sequences!=(saved.record.raw['sequence'],)*2:
                    raise RuntimeError('25Hz一对一原始来源不符')
                runtime=chain.step(slot); finished=self.clock.monotonic_ns()
                # pair is a one-record tuple in this schema; existing journal
                # accesses only first/last and records equal source endpoints.
                result=ProcessedSlot((saved,),slot,runtime,started,finished,
                                     measured.last_call_ns,self.clock.monotonic_ns())
                with self._lock:
                    guarded=self._guard_result(result,finished).runtime.frame
                    result=replace(result,publication_allowed=guarded.output_allowed,
                                   publication_bpm=guarded.bpm,publication_reason=guarded.reason_cn)
                    self._counts['processed']+=1; self._latest=result; self._history.append(result)
                self._offer_result(result)
        except Exception as exc: self._fail('processing',str(exc))
        finally:
            self._processor_ready.set()
            if measured is not None and (self._fault is None or self._fault.stage!='processing'):
                try: self._pl_snapshot=measured.snapshot()
                except Exception as exc:
                    self._pl_snapshot_error=str(exc); self._fail('pl_final_snapshot',str(exc))
            else: self._pl_snapshot_error='后端故障，未重试快照／未reset清计数'
            try: self._close_processing_chain()
            except Exception as exc: self._fail('processing_cleanup',str(exc))
            self._processor_done.set()

    def _make_summary(self,cleanup_complete,display_metrics=None):
        with self._lock:
            result=IsolatedLiveSession._make_summary(self,cleanup_complete,display_metrics)
            audit=self._frontend.audit()
            unadapted=result['raw_saved']-audit['raw_received']
            unfinished=audit['slots_emitted']-result['processed']
            unprocessed=result['raw_saved']-result['processed']
            result.update(schema=VERSION,raw_hz=25,processing_hz=25,adc_hz=50,fifo_sample_average=2,
                peak_version='fractional_peaks_v2',frontend=audit,
                raw_safety=asdict(self._safety.snapshot()),unadapted_saved_raw=unadapted,
                formed_unprocessed_slots=unfinished,unprocessed_raw=unprocessed,
                consumed_raw_by_results=result['processed'],capture_loop_overruns=self._overruns25,
                capture_loop_budget_ns=40_000_000,
                count_identity=(audit['count_identity'] and min(unadapted,unfinished,unprocessed)>=0
                                and unprocessed==unadapted+unfinished),
                processing_queue_unit='raw_records',processing_queue_capacity=250,
                live_25hz_passed=False,live_50hz_passed=False,
                display_age_guard_ns=1_000_000_000,display_age_limit_frozen=False,
                input_filter='max30102_average2_not_equivalent_to_fir21',
                timestamp_scope='host_observation_not_adc_center',antialias_equivalence_passed=False)
            return result
