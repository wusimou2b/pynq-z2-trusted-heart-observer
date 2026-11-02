"""Session-scoped manual stop; submitted is never equivalent to released."""
import json
from pathlib import Path
import re
import time
from zipfile import ZipFile


def atomic_state(path, value):
    path = Path(path)
    pending = path.with_suffix('.pending')
    with pending.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
    pending.replace(path)


class StopControl:
    def __init__(self, directory, token, *, clock_ns=time.monotonic_ns):
        if not re.fullmatch('[0-9a-f]{32}', token):
            raise ValueError('invalid session token')
        self.directory, self.token, self.clock_ns = Path(directory), token, clock_ns
        self.directory.mkdir(parents=True, exist_ok=False)
        self.accepted_ns = self.request = None
        self.next_poll_ns = 0
        self.state = dict(schema='v3b25_continuous_state_v1', token=token,
                          phase='prepared', cleanup_complete=False, export_complete=False)
        self._write()

    def _write(self):
        atomic_state(self.directory/'state.json', self.state)

    def mark(self, phase):
        if phase not in ('starting', 'running', 'stopping', 'shutdown_incomplete', 'export_failed'):
            raise RuntimeError('terminal state requires actual cleanup and export')
        if self.state['export_complete']:
            raise RuntimeError('session already finished; no restart')
        self.state['phase'] = phase
        self._write()

    def poll(self, stop, manual, *, force=False):
        if self.accepted_ns is not None:
            return False
        now = self.clock_ns()
        if not force and now < self.next_poll_ns:
            return False
        self.next_poll_ns = now + 100_000_000
        path = self.directory/'request.json'
        if not path.exists():
            return False
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError('invalid stop request file')
        request = json.loads(path.read_text('utf-8'))
        if not (isinstance(request, dict)
                and request.get('schema') == 'v3b25_manual_stop_request_v1'
                and request.get('token') == self.token and request.get('action') == 'stop'
                and isinstance(request.get('request_id'), str)
                and re.fullmatch('[0-9a-f]{32}', request['request_id'])):
            raise ValueError('stop request does not belong to this session')
        self.request, self.accepted_ns = request, now
        manual.set()
        stop.set()
        self.state.update(accepted_ns=now, request_id=request['request_id'])
        self.mark('stopping')
        return True

    def finish(self, result, archive):
        cancelled = result.get('cancelled_before_owner') is True and result.get('hardware_never_started') is True
        if not result.get('resources_released') or not (result.get('owner_exited') or cancelled):
            self.mark('shutdown_incomplete')
            raise RuntimeError('owner/resource release not confirmed; no completed status')
        with ZipFile(archive) as z:
            if len(z.namelist()) != len(set(z.namelist())) or z.testzip() is not None:
                raise ValueError('export ZIP incomplete')
        phase = 'cancelled_before_start' if cancelled else ('stopped' if result['manual_session_passed'] else 'stopped_with_errors')
        self.state.update(phase=phase,
                          cleanup_complete=True, export_complete=True, archive=Path(archive).name,
                          export_completed_ns=self.clock_ns())
        self._write()


def assess_manual(summary, owner, *, parent_error, requested, owner_exitcode):
    """Independent manual-run judgement; leave the original sixty-second audit alone."""
    isolation = summary.get('isolation') or {}
    video, cleanup = owner.get('video') or {}, owner.get('cleanup') or {}
    dma = cleanup.get('dma') or {}
    released = bool(owner_exitcode is not None and summary.get('cleanup_complete')
        and owner.get('inherited_cleanup_complete') and cleanup.get('cleanup_complete')
        and dma and all(x.get('halted') and x.get('error_bits') == 0 for x in dma.values())
        and owner.get('actual_lease_released') is True
        and owner.get('quarantine_required') is False and owner.get('retention_reasons') == []
        and (video.get('cleanup') or {}).get('cleanup_complete'))
    gates = (summary.get('audit25') or {}).get('gates') or {}
    count = summary.get('read', 0)
    checks = dict(manual_request=requested is True, manual_stop=summary.get('stop_reason') == 'manual_stop',
        no_original_fault=summary.get('fault') is None and summary.get('state') == 'stopped',
        no_parent_error=parent_error is None, owner_natural_exit=owner_exitcode == 0,
        no_wrapper_error=owner.get('wrapper_error') is None,
        original_gates=bool(gates) and all(v is True for k,v in gates.items() if k != 'full_duration'),
        exact_counts=count > 0 and all(summary.get(k) == count for k in ('processed','raw_saved','results_saved')),
        rate_25=summary.get('raw_hz') == summary.get('processing_hz') == 25,
        manual_mode=(summary.get('preflight') or {}).get('continuous_mode') == 'manual_until_stop_v1',
        queues_drained=summary.get('queues_drained') is True,
        ps_natural_exit=isolation.get('forced_termination') is False and isolation.get('exitcode') == 0
            and isolation.get('cleanup_complete') is True
            and isolation.get('completed_steps') == isolation.get('pl_requests') == count,
        identities=owner.get('inputs_unchanged') is True and owner.get('identity_error') is None,
        video_clean=video.get('fault') is None and video.get('thread_exited') is True
            and video.get('target_application_fps') == 5 and video.get('requested_formal_seconds') is None
            and video.get('continuous_mode') == 'manual_until_stop_v1',
        resources_released=released)
    return dict(schema='v3b25_continuous_result_v1', checks=checks,
        manual_session_passed=all(checks.values()), resources_released=released,
        owner_exited=owner_exitcode is not None, strict_realtime_verified=False,
        accuracy_verified=False, board_ddr_verified=False, full_v3b_acceptance_passed=False)


def audit_artifacts(directory, summary, owner):
    """Keep existing non-duration video/adapter/display gates after all writers exit."""
    if __package__:
        from .yuyv_joint_guard import assess_yuyv_video, audit_yuyv
    else:
        from yuyv_joint_guard import assess_yuyv_video, audit_yuyv
    directory = Path(directory)
    video = owner.get('video') or {}
    vg = assess_yuyv_video(video)
    journal = audit_yuyv(directory/'video', video)
    snap, pre = owner.get('snapshot') or {}, summary.get('preflight') or {}
    display_gates = (summary.get('display_audit') or {}).get('gates') or {}
    checks = dict(video_original=bool(vg) and all(vg.values()),
        video_journal=journal['error'] is None and all(journal['checks'].values()),
        video_manual_admission=False, video_common_epoch=False,
        original_display=bool(display_gates) and all(display_gates.values()),
        recovered_iic=owner.get('iic_runtime') == pre.get('iic_runtime') == 'original_pynq_sensorbus'
            and owner.get('native_iic_started') is False and pre.get('native_iic_started') is False,
        no_probe=owner.get('snapshot_probe_started') is False and pre.get('snapshot_probe_started') is False,
        original_snapshot=snap.get('installed') is True and snap.get('restored') is True
            and snap.get('final_snapshot_constructions') == 1 and snap.get('original_guard_retained') is True
            and snap.get('status_cached') is False and owner.get('snapshot_cleanup_confirmed') is True,
        original_binding=owner.get('binding_installed') is True and owner.get('prepare_calls') == 1
            and pre.get('video_shares_existing_owner') is True and pre.get('concurrent_video_target_fps') == 5,
        no_adapter_errors=all(owner.get(k) is None for k in ('install_error','restore_error','prepare_error','release_error')),
        gc_restored=False, frozen_entry=False)
    errors = []
    try:
        epoch, end, m = video['formal_started_ns'], video['video_loop_ended_ns'], video['metrics']
        checks['video_common_epoch'] = bool(epoch == summary['startup']['started_ns'] and type(epoch) is int
            and video['formal_deadline_ns'] is None and video['requested_formal_seconds'] is None
            and video['continuous_mode'] == 'manual_until_stop_v1' and video['target_application_fps'] == 5)
        previous = -1
        n = tail = 0
        valid = True
        with (directory/'video/frames.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                slot = row['target_slot']
                valid &= bool(type(slot) is int and slot > previous
                    and epoch <= row['grab_completed_ns'] <= row['admitted_ns'] == row['read_completed_ns']
                    <= row['submitted_ns'] <= end and row['grab_completed_ns'] >= epoch+slot*200_000_000
                    and row['completed_after_formal_end'] is False)
                previous = slot
                n += 1
                tail += int(row.get('completed_after_stop_request',False))
        checks['video_manual_admission'] = bool(n >= 3 and valid and previous+1-n == m['missed_target_slots']
            and n == m['selected_grabs'] == m['completed_frames'] == m['records_saved']
            and m['grabs_total'] == m['preparation_grabs']+m['formal_grabs']+m['terminal_grabs']
            and m['formal_grabs'] == m['selected_grabs']+m['unselected_formal_grabs']+m['terminal_retrieves']
            and m['tail_completed_frames'] == tail and m['formal_submitted_frames'] == n-tail)
        gc_report = json.loads((directory/'owner_gc_window.json').read_text('utf-8'))
        window = gc_report.get('window') or {}
        checks['gc_restored'] = bool(gc_report.get('install_error') is None and gc_report.get('wrapper_error') is None
            and window.get('restored') is True and not window.get('errors'))
        entry = json.loads((directory/'owner_entry25.json').read_text('utf-8'))
        checks['frozen_entry'] = bool(entry.get('worker_binding_installed') is True
            and entry.get('entry_files_unchanged') is True and entry.get('wrapper_error') is None)
    except Exception as exc:
        errors.append(dict(type=type(exc).__name__,message=str(exc)))
    return dict(checks=checks,video_checks=vg,video_journal=journal,errors=errors)
