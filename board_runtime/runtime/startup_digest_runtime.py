"""Remove repeated SHA work before the original StartupTrace, without moving deadlines."""
from contextlib import contextmanager
from functools import partial
import hashlib
import json
from pathlib import Path
import time

from startup_digest import StartupDigests


@contextmanager
def prefix_digest_scope(startup, directory, *, worker_entry_ns=None, candidate_validation_ns=None):
    original_hash, original_trace = hashlib.sha256, startup.StartupTrace
    cache = StartupDigests(original_hash)
    started_ns = time.monotonic_ns()
    state = dict(barrier_reached=False, report_written=False)
    def restore():
        cache.close()
        hashlib.sha256 = original_hash
        startup.StartupTrace = original_trace
    def report():
        value = dict(schema='startup_exact_bytes_digest_v1', **state, **cache.report(),
            elapsed_ns=time.monotonic_ns()-started_ns, cache_scope='before_original_StartupTrace_only',
            worker_entry_ns=worker_entry_ns, candidate_validation_ns=candidate_validation_ns,
            worker_entry_to_report_ns=None if worker_entry_ns is None else time.monotonic_ns()-worker_entry_ns,
            path_or_stat_cache=False, every_file_read_retained=True, original_checks_retained=True,
            original_hash_restored=hashlib.sha256 is original_hash, startup_timeout_seconds=180,
            deadline_moved=False, warmup_slots=700, automatic_retry=False)
        with (Path(directory)/'startup-digest-prefix.json').open('x',encoding='utf-8') as stream:
            json.dump(value,stream,indent=2,allow_nan=False)
        state['report_written'] = True
    def barrier(*args, **kwargs):
        state['barrier_reached'] = True
        restore()
        report()
        return original_trace(*args, **kwargs)
    hashlib.sha256, startup.StartupTrace = cache, barrier
    failure = None
    try:
        yield state
    except BaseException as exc:
        failure = exc
        raise
    finally:
        restore()
        if not state['report_written']:
            try:
                report()
            except BaseException as report_error:
                if failure is None:
                    raise
                print('Preserved original prefix failure; digest report also failed: '+str(report_error),flush=True)


def worker(*args,root,expected_startup_manifest_sha256,**kwargs):
    entered_ns=time.monotonic_ns()
    from startup_digest_guard import verify
    verify(root,expected_startup_manifest_sha256)
    validated_ns=time.monotonic_ns()
    import joint_startup_worker
    from fifo_time_runtime import worker as original
    with prefix_digest_scope(joint_startup_worker,args[1],worker_entry_ns=entered_ns,
                             candidate_validation_ns=validated_ns-entered_ns):
        return original(*args,root=root,**kwargs)


def start_owner(context,*args,root,expected_startup_manifest_sha256,**kwargs):
    from startup_digest_guard import verify
    if Path(root).resolve()!=Path(__file__).resolve().parent:
        raise ValueError('startup digest owner root differs')
    verify(root,expected_startup_manifest_sha256)
    child=context.Process(target=partial(worker,root=root,
        expected_startup_manifest_sha256=expected_startup_manifest_sha256,**kwargs),
        args=args,name='joint25-fifo-startup-exact-bytes',daemon=False)
    child.start()
    return child
