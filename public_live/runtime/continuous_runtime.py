"""Owner-local manual duration; original physical preparation and PS target stay intact."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
import json
from types import MethodType

@dataclass(frozen=True)
class ManualSettings:
    mode: str = 'baseline'
    protocol: str = 'static'
    duration_seconds: object = None

def capture_until_stopped(self):
    started_ns = None
    try:
        self._startup = self.source.begin()
        started_ns = self._startup['started_ns']
        with self._lock:
            if self._fault is None and (not self._stop_requested.is_set()):
                self._state = 'running'
        self._capture_ready.set()
        while not self._stop_requested.is_set():
            try:
                batch = self.source.read_batch()
            except StopIteration:
                self._request_stop('finite_input_complete')
                break
            with self._lock:
                size = len(batch.records)
                self._counts['read'] += size
                self._counts['batches'] += 1
                self._counts['max_fifo_batch'] = max(size, self._counts['max_fifo_batch'])
                for record in batch.records:
                    paired = record.raw['pair_ok']
                    self._counts['paired' if paired else 'unpaired'] += 1
                    phase = str(record.raw['phase'])
                    self._phase_counts[phase] = self._phase_counts.get(phase, 0) + int(paired)
                if batch.records:
                    first = batch.records[0].raw
                    self._counts['capture_loop_overruns'] += int(first['capture_loop_ns'] > 20000000)
                    self._counts['max30102_overflow_events'] += int(first['max30102_overflow'] > 0)
                    self._counts['max30102_overflow_count'] += first['max30102_overflow']
            if not self._offer(self._raw_queue, batch, 'raw'):
                self._terminal_batch = batch
                break
            if batch.fault:
                fault = batch.fault
                with self._lock:
                    self._counts['sensor_errors'] += int(fault.reason == 'sensor_read_exception')
                    self._counts['acceleration_invalid_events'] += int(fault.stage == 'mpu_acceleration_read')
                    self._counts['pl_fifo_errors'] += int(fault.stage == 'axi_fifo_loopback')
                    self._counts['timestamp_errors'] += int(fault.stage == 'timestamp_reconstruction')
                    self._counts['timestamp_rejected_samples'] += size if fault.stage == 'timestamp_reconstruction' else 0
                    self._counts['consumed_ppg_unknown'] |= bool(fault.details.get('consumed_ppg_unknown'))
                self._fail(fault.stage, fault.reason, fault.sequence, self._continuous_plain(fault.details))
                break
    except Exception as exc:
        self._fail('capture', str(exc), details=dict(consumed_ppg_unknown=True))
        with self._lock:
            self._counts['sensor_errors'] += 1
            self._counts['consumed_ppg_unknown'] = True
    finally:
        if started_ns is not None:
            self._elapsed_seconds = (self.clock.monotonic_ns() - started_ns) / 1000000000.0
        self._producer_closed.set()
        self._capture_ready.set()
        self._request_stop('capture_finished')

def make_video_class():
    if __package__:
        from .joint_video_five import VideoFive, PERIOD_NS
        from .joint_video_runtime import describe
    else:
        from joint_video_five import VideoFive, PERIOD_NS
        from joint_video_runtime import describe

    class ManualVideo(VideoFive):

        def request_stop(self):
            if not self._stop.is_set():
                self.manual_stop_requested_ns = self.clock_ns()
            super().request_stop()

        def run(self):
            if self._attempted:
                raise RuntimeError('video loop already attempted')
            self._attempted = True
            self._active = True
            m, slot = (self.metrics, 0)
            try:
                with (self.output / 'frames.jsonl').open('x', encoding='utf-8') as sink:
                    self._ready.set()
                    while not self._stop.is_set():
                        if not self.resources.camera.grab():
                            raise RuntimeError('camera grab failed; no retry')
                        grabbed_ns = self.clock_ns()
                        grab_sequence = m['grabs_total']
                        m['grabs_total'] += 1
                        epoch = self.started_ns
                        if epoch is None or grabbed_ns < epoch:
                            m['preparation_grabs'] += 1
                            continue
                        m['formal_grabs'] += 1
                        due = epoch + slot * PERIOD_NS
                        if grabbed_ns < due or self._stop.is_set():
                            m['unselected_formal_grabs'] += 1
                            continue
                        missed = max(0, (grabbed_ns - due) // PERIOD_NS)
                        slot += missed
                        m['missed_target_slots'] += missed
                        ok, bgr = self.resources.camera.retrieve()
                        read_ns = self.clock_ns()
                        if not ok:
                            raise RuntimeError('camera retrieve failed; no retry')
                        if self._stop.is_set():
                            m['terminal_retrieves'] += 1
                            break
                        m['selected_grabs'] += 1
                        if self.first_admitted_ns is None:
                            self.first_admitted_ns = read_ns
                        self.last_admitted_ns = read_ns
                        began = self.clock_ns()
                        row = self.resources.process_ready_frame(bgr, sequence=m['completed_frames'], timestamp_ns=read_ns)
                        submitted_ns = self.clock_ns()
                        tail = self._stop.is_set()
                        row.update(camera_grab_sequence=grab_sequence, grab_completed_ns=grabbed_ns, admitted_ns=read_ns, submitted_ns=submitted_ns, target_slot=slot, completed_after_formal_end=False, completed_after_stop_request=tail)
                        sink.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                        sink.flush()
                        m['completed_frames'] += 1
                        m['records_saved'] += 1
                        m['valid_difference_frames'] += int(row['vision']['difference_valid'])
                        m['formal_submitted_frames'] += int(not tail)
                        m['tail_completed_frames'] += int(tail)
                        m['max_frame_processing_ms'] = max(m['max_frame_processing_ms'], (submitted_ns - began) / 1000000.0)
                        if self.first_submitted_ns is None:
                            self.first_submitted_ns = submitted_ns
                        self.last_submitted_ns = submitted_ns
                        slot += 1
            except BaseException as exc:
                self.fault = describe(exc, 'video_thread')
                self.stop_reason = 'fault'
            finally:
                self.ended_ns = self.clock_ns()
                if self.started_ns is not None:
                    m['formal_elapsed_seconds'] = max(0, self.ended_ns - self.started_ns) / 1000000000.0
                    if m['formal_elapsed_seconds']:
                        m['application_submit_fps'] = m['formal_submitted_frames'] / m['formal_elapsed_seconds']
                if self.stop_reason is None:
                    self.stop_reason = 'stop_requested'
                self._active = False
                self._ready.set()

        def report(self):
            result = super().report()
            result.update(continuous_mode='manual_until_stop_v1', requested_formal_seconds=None, formal_deadline_ns=None, target_period_ns=PERIOD_NS, video_stop_requested_ns=getattr(self, 'manual_stop_requested_ns', None))
            return result
    return ManualVideo

@contextmanager
def install_manual_runtime(manual):
    if __package__:
        from . import heart_video_binding as binding, joint_concurrent_owner as flow
        from .joint_startup import replace_attribute
    else:
        import heart_video_binding as binding, joint_concurrent_owner as flow
        from joint_startup import replace_attribute
    original = binding.SnapshotVideoBinding.prepare
    original_dependencies = flow._dependencies
    loop_class = make_video_class()

    def prepare(self, *args, **kwargs):
        self.loop_factory = loop_class
        return original(self, *args, **kwargs)

    def adapt(session):
        try:
            settings = session.settings
            if (settings.mode, settings.protocol, settings.duration_seconds) != ('baseline', 'static', 60):
                raise ValueError('manual settings baseline differs')
            session._continuous_plain = session._capture_loop.__func__.__globals__['plain']
            session.settings = ManualSettings()
            session._capture_loop = MethodType(capture_until_stopped, session)
            original_stop = session._request_stop

            def request_stop(reason):
                if manual.is_set() and session._fault is None and (reason in ('display_finished', 'display_stopped_before_start')):
                    reason = 'manual_stop'
                return original_stop(reason)
            session._request_stop = request_stop
            session._preflight.update(continuous_mode='manual_until_stop_v1', formal_duration_seconds=None)
        except BaseException as exc:
            session._fail('continuous_install', str(exc) or type(exc).__name__)
        return session

    def dependencies():
        deps = original_dependencies()
        original_prepare = deps.prepare

        def prepared(*args, **kwargs):
            return adapt(original_prepare(*args, **kwargs))
        deps.prepare = prepared
        return deps
    with replace_attribute(binding.SnapshotVideoBinding, 'prepare', prepare), replace_attribute(flow, '_dependencies', dependencies):
        yield

def owner_worker(*args, root, source, manual, manifest_sha, release_contract=None):
    if release_contract is not None:
        manifest_sha = release_contract['expected_manifest_sha256']
    if __package__:
        from .continuous_guard import verify_additions
        from .lean_ps_worker import owner_worker as original
    else:
        from continuous_guard import verify_additions
        from lean_ps_worker import owner_worker as original
    verify_additions(root, manifest_sha) if release_contract is None else verify_boundary(root, release_contract)
    with install_manual_runtime(manual):
        return original(*args, root=root, source=source, release_contract=release_contract)

def start_owner(context, *args, root, source, manual, manifest_sha, release_contract=None):
    if release_contract is not None:
        manifest_sha = release_contract['expected_manifest_sha256']
    child = context.Process(target=partial(owner_worker, root=root, source=source, manual=manual, manifest_sha=manifest_sha, release_contract=release_contract), args=args, name='joint25-continuous-owner', daemon=False)
    child.start()
    return child
