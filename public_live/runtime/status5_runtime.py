"""Observe the actual owner path; do not replace its active SnapshotAdapter."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager
import ctypes as C
from functools import partial
from pathlib import Path
import threading
import time
FORMAL_SECONDS = 5
STAGES = {'loop_gap': 1, 'lock': 2, 'snapshot': 3, 'publish': 4, 'sleep': 5}

class _Row(C.Structure):
    _fields_ = [('kind', C.c_uint32), ('error', C.c_uint32), ('begin', C.c_uint64), ('end', C.c_uint64), ('cpu_begin', C.c_uint64), ('cpu_end', C.c_uint64)]

class Trace:

    def __init__(self, stop, *, wall=time.monotonic_ns, cpu=time.thread_time_ns, capacity=8192):
        if type(capacity) is not int or not 1 <= capacity <= 8192:
            raise ValueError('bounded trace required')
        self.stop, self.wall, self.cpu = (stop, wall, cpu)
        self.owner = threading.get_ident()
        self.buffer = (_Row * capacity)()
        self.capacity = capacity
        self.count = 0
        self.overflow = False
        self.first_error = None
        self.last_publish = self.last_publish_cpu = None
        self.formal_epoch = self.cutoff_ns = self.active_snapshot = None

    def _begin(self, stage):
        if self.count == self.capacity:
            self.overflow = True
            self.stop.set()
            return None
        row = self.buffer[self.count]
        self.count += 1
        row.kind = STAGES[stage]
        row.begin = self.wall()
        row.cpu_begin = self.cpu()
        return row

    def measure(self, stage, call, *args, **kwargs):
        if threading.get_ident() != self.owner:
            return call(*args, **kwargs)
        row = self._begin(stage)
        try:
            return call(*args, **kwargs)
        except BaseException as exc:
            if row is not None:
                row.error = 1
            if self.first_error is None:
                self.first_error = dict(stage=stage, type=type(exc).__name__, message=str(exc))
            raise
        finally:
            if row is not None:
                row.cpu_end = self.cpu()
                row.end = self.wall()
                if stage == 'publish':
                    self.last_publish, self.last_publish_cpu = (row.end, row.cpu_end)

    def enter_snapshot(self):
        if self.last_publish is not None:
            row = self._begin('loop_gap')
            if row is not None:
                row.end = row.begin
                row.begin = self.last_publish
                row.cpu_end = row.cpu_begin
                row.cpu_begin = self.last_publish_cpu

    def check_cap(self, session, snapshot):
        if snapshot.state != 'running':
            return
        epoch = getattr(session, '_startup', {}).get('started_ns')
        if type(epoch) is not int or epoch < 0:
            raise ValueError('actual formal epoch missing')
        if self.formal_epoch is None:
            self.formal_epoch = epoch
        if epoch != self.formal_epoch:
            raise ValueError('actual formal epoch changed')
        now = self.wall()
        if now - epoch >= FORMAL_SECONDS * 1000000000 and self.cutoff_ns is None:
            self.cutoff_ns = now
            self.stop.set()

    def rows(self):
        names = {v: k for k, v in STAGES.items()}
        return [dict(stage=names[r.kind], begin_ns=r.begin, end_ns=r.end, wall_ns=r.end - r.begin if r.end else None, thread_cpu_ns=r.cpu_end - r.cpu_begin if r.end else None, error=bool(r.error)) for r in self.buffer[:self.count]]

    def report(self):
        rows = self.rows()
        summary = {}
        for name in STAGES:
            selected = [r for r in rows if r['stage'] == name and r['end_ns']]
            summary[name] = dict(count=len(selected), max_wall_ms=max((r['wall_ns'] for r in selected), default=0) / 1000000.0, max_thread_cpu_ms=max((r['thread_cpu_ns'] for r in selected), default=0) / 1000000.0)
        return dict(schema='actual_joint_status_trace_v1', records=rows, summary=summary, capacity=self.capacity, overflow=self.overflow, first_error=self.first_error, formal_observation_seconds=FORMAL_SECONDS, formal_epoch_ns=self.formal_epoch, short_cap_requested_ns=self.cutoff_ns, active_snapshot=self.active_snapshot, clock_domains=dict(wall='monotonic_ns', cpu='observing_owner_thread_time_ns_not_PS_child'), scope='Instrumented actual joint owner; loop_gap includes intended sleep/checks. Wall-minus-CPU is not IPC or proof of GIL.', live25_acceptance_passed=False, full_v3b_acceptance_passed=False)

class ObservedLock:

    def __init__(self, original, trace):
        self.original, self.trace = (original, trace)

    def acquire(self, *args, **kwargs):
        return self.trace.measure('lock', self.original.acquire, *args, **kwargs)

    def release(self):
        return self.original.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()

    def __getattr__(self, name):
        return getattr(self.original, name)

@contextmanager
def observe_session(session, trace):
    present = 'snapshot' in vars(session)
    previous = vars(session).get('snapshot')
    snapshot = session.snapshot
    lock = session._lock
    trace.active_snapshot = getattr(snapshot, '__qualname__', type(snapshot).__name__)

    def observed(*args, **kwargs):
        trace.enter_snapshot()
        value = trace.measure('snapshot', snapshot, *args, **kwargs)
        trace.check_cap(session, value)
        return value
    session._lock = ObservedLock(lock, trace)
    session.snapshot = observed
    try:
        yield
    finally:
        session._lock = lock
        if present:
            session.snapshot = previous
        else:
            del session.snapshot

class ObservedMailbox:

    def __init__(self, original, trace):
        self.original, self.trace = (original, trace)

    def publish(self, *args, **kwargs):
        return self.trace.measure('publish', self.original.publish, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.original, name)

def observed_sleep(sleep, trace):

    def sleeping(seconds):
        return trace.measure('sleep', sleep, seconds)
    return sleeping

def observed_main(original, module, trace, *args, **kwargs):
    """The original owner controls start, heartbeat, joins, PS close and release."""
    from contextlib import ExitStack
    from types import SimpleNamespace as N
    dependencies = kwargs.pop('dependencies', None) or module._dependencies()
    actual_prepare = dependencies.prepare
    with ExitStack() as stack:

        def prepare(*a, **kw):
            session = actual_prepare(*a, **kw)
            stack.enter_context(observe_session(session, trace))
            return session
        deps = N(**vars(dependencies))
        deps.prepare = prepare
        values = list(args)
        values[3] = ObservedMailbox(values[3], trace)
        return original(*values, dependencies=deps, sleep=observed_sleep(kwargs.pop('sleep', time.sleep), trace), **kwargs)

def owner_worker(*args, release_contract=None, **kwargs):
    if __package__:
        from . import sample40_runtime as original, joint_concurrent_owner as owner
        from .joint_startup import replace_attribute
        from .run_status5 import verify_package, write_new
        from .joint_concurrent_worker import system_resources
    else:
        import sample40_runtime as original, joint_concurrent_owner as owner
        from joint_startup import replace_attribute
        from run_status5 import verify_package, write_new
        from joint_concurrent_worker import system_resources
    verify_package(kwargs['root']) if release_contract is None else verify_boundary(kwargs['root'], release_contract)
    trace = Trace(args[3])
    failure = None
    actual = owner.owner_main
    resources_before = system_resources()

    def traced(*a, **kw):
        return observed_main(actual, owner, trace, *a, **kw)
    try:
        with replace_attribute(owner, 'owner_main', traced):
            return original.owner_worker(*args, **kwargs, release_contract=release_contract)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        report = trace.report()
        report.update(original_error=None if failure is None else dict(type=type(failure).__name__, message=str(failure)), resources_before=resources_before, resources_after=system_resources(), per_sample_ipc_added=0, hot_path_file_writes=0, original_snapshot_adapter_retained=True)
        try:
            write_new(Path(args[1]) / 'status5-owner.json', report)
        except BaseException as export_error:
            if failure is not None:
                raise failure from export_error
            raise

def start_owner(context, *args, release_contract=None, **kwargs):
    child = context.Process(target=partial(owner_worker, **kwargs, release_contract=release_contract), args=args, name='joint25-status-five-second-observer', daemon=False)
    child.start()
    return child
