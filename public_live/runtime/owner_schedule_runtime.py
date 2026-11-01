"""Scope a shorter GIL interval to one disposable hardware-owner process."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager
from functools import partial
import gc
import json
from pathlib import Path
import sys
if __package__:
    from .owner_schedule_guard import verify, SOURCE_SHA
    from .owner_timeslice import owner_timeslice
    from .owner_display_copy import bulk_owner_writer
else:
    from owner_schedule_guard import verify, SOURCE_SHA
    from owner_timeslice import owner_timeslice
    from owner_display_copy import bulk_owner_writer

@contextmanager
def replaced(module, name, value):
    old = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, old)

def verified_ps_worker(connection, backend_source, *, root, expected_schedule_manifest_sha256, expected_reuse_manifest_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        expected_schedule_manifest_sha256 = release_contract['expected_manifest_sha256']
        expected_reuse_manifest_sha256 = release_contract['expected_manifest_sha256']
    if release_contract is None and expected_reuse_manifest_sha256 != SOURCE_SHA:
        raise ValueError('retained PS source differs')
    verify(root, expected_schedule_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    from evidence_reuse_runtime import verified_ps_worker as original

    class ReadyConnection:

        def send(self, message):
            if message[:2] == (0, 'ready'):
                message = (0, 'ready', dict(message[2], owner_schedule_ps=dict(manifest_sha256=expected_schedule_manifest_sha256, manifest_verified_before_original=True, switch_seconds=sys.getswitchinterval(), switch_changed_in_ps=False)))
            return connection.send(message)

        def __getattr__(self, name):
            return getattr(connection, name)
    return original(ReadyConnection(), backend_source, root=root, expected_reuse_manifest_sha256=SOURCE_SHA, **kwargs, release_contract=release_contract)

def worker(*args, root, expected_schedule_manifest_sha256, expected_reuse_manifest_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        expected_schedule_manifest_sha256 = release_contract['expected_manifest_sha256']
        expected_reuse_manifest_sha256 = release_contract['expected_manifest_sha256']
    if release_contract is None and expected_reuse_manifest_sha256 != SOURCE_SHA:
        raise ValueError('retained owner source differs')
    verify(root, expected_schedule_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    import evidence_reuse_runtime as original
    before = sys.getswitchinterval()
    gc_before = (gc.isenabled(), gc.get_threshold())
    failure = None
    try:
        with owner_timeslice(0.001), bulk_owner_writer(), replaced(original, 'verified_ps_worker', partial(verified_ps_worker, expected_schedule_manifest_sha256=expected_schedule_manifest_sha256, release_contract=release_contract)):
            return original.worker(*args, root=root, expected_reuse_manifest_sha256=SOURCE_SHA, **kwargs, release_contract=release_contract)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        report = dict(schema='scoped_owner_schedule_v1', owner_switch_seconds=0.001, before_seconds=before, after_seconds=sys.getswitchinterval(), interval_restored=sys.getswitchinterval() == before, gc_unchanged=gc_before == (gc.isenabled(), gc.get_threshold()), ps_child_switch_changed=False, original_timeouts_unchanged=True, ipc_protocol_changed=False, automatic_retry=False, display_bulk_writer=True, display_lock_seconds=0.05, display_status_age_ns=100000000, manifest_sha256=expected_schedule_manifest_sha256, original_error=None if failure is None else dict(type=type(failure).__name__, message=str(failure)))
        directory = Path(args[1])
        if directory.is_dir():
            try:
                with (directory / 'owner-schedule.json').open('x', encoding='utf-8') as stream:
                    json.dump(report, stream, ensure_ascii=False, indent=2)
            except BaseException as exc:
                if failure is not None:
                    raise failure from exc
                raise

def start_owner(context, *args, root, expected_schedule_manifest_sha256, expected_reuse_manifest_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        expected_schedule_manifest_sha256 = release_contract['expected_manifest_sha256']
        expected_reuse_manifest_sha256 = release_contract['expected_manifest_sha256']
    if Path(root).resolve() != Path(__file__).resolve().parent:
        raise ValueError('schedule owner root differs')
    verify(root, expected_schedule_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    process = context.Process(target=partial(worker, root=root, expected_schedule_manifest_sha256=expected_schedule_manifest_sha256, expected_reuse_manifest_sha256=expected_reuse_manifest_sha256, **kwargs, release_contract=release_contract), args=args, name='joint25-scoped-owner-schedule', daemon=False)
    process.start()
    return process
