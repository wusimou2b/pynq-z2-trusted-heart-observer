"""Manual duration and enlarged schedule storage; retained processing/cleanup."""
from contextlib import contextmanager
from functools import partial
import json
from pathlib import Path
from demo_continuous_guard import verify


@contextmanager
def timer_scope():
    import status60_runtime as status
    original = status.Trace
    audit = dict(instances=0, restored=False, automatic_formal_stop=False,
        epoch_validation=True, trace_overflow_stop_preserved=True)

    class ManualTrace(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            audit['instances'] += 1

        def check_cap(self, session, snapshot):
            if snapshot.state != 'running': return
            epoch = getattr(session, '_startup', {}).get('started_ns')
            if type(epoch) is not int or epoch < 0:
                raise ValueError('actual formal epoch missing')
            if self.formal_epoch is None: self.formal_epoch = epoch
            if epoch != self.formal_epoch: raise ValueError('actual formal epoch changed')
            # No deadline here. The original manual/fault stop Event, trace
            # capacity and every other owner/session guard remain unchanged.

        def report(self):
            return dict(super().report(), formal_observation_seconds=None,
                formal_cap_enabled=False, duration_mode='manual_until_stop_v1')

    status.Trace = ManualTrace
    try: yield audit
    finally:
        status.Trace = original
        audit['restored'] = True


def owner_worker(*args, root, demo_expected, **kwargs):
    # Spawn imports only stdlib + the pure guard before verification.
    verify(demo_expected, root)
    from route_live_runtime import owner_worker as retained
    from demo_schedule_capacity import capacity_scope
    failure = None
    try:
        with timer_scope() as audit, capacity_scope():
            return retained(*args, root=root, **kwargs)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        # Retained quarantine does not return here until it releases resources.
        if len(args) > 1 and Path(args[1]).is_dir():
            report = dict(schema='continuous_demo_owner_v1', manifest_sha256=demo_expected,
                timer=locals().get('audit'),
                scheduling_record_capacity=8192, extra_preallocated_bytes=393216,
                error=None if failure is None else dict(type=type(failure).__name__, message=str(failure)),
                other_protections_changed=False, automatic_retry=False)
            try:
                with (Path(args[1])/'demo-continuous-owner.json').open('x', encoding='utf-8') as stream:
                    json.dump(report, stream, ensure_ascii=False, indent=2)
            except BaseException as export_error:
                if failure is not None: raise failure from export_error
                raise


def start_owner(context, *args, root, demo_expected, **kwargs):
    verify(demo_expected, root)
    from lean_ps_exit_trace import make_shared
    stages = make_shared()
    process = context.Process(target=partial(owner_worker, root=root,
        demo_expected=demo_expected, exit_stages=stages, **kwargs),
        args=args, name='joint25-continuous-demo-owner', daemon=False)
    process.start()
    return process


@contextmanager
def parent_scope(root, expected):
    verify(expected, root)
    import route_live_runtime as route
    original = route.start_owner
    route.start_owner = partial(start_owner, demo_expected=expected)
    try: yield
    finally: route.start_owner = original
