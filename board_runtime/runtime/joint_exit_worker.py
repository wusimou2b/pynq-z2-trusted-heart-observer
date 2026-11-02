"""Exit-only hooks on the original Lean joint owner; close caller owns trace."""
from contextlib import ExitStack
from functools import partial
import os
from pathlib import Path
import sys
import threading
from types import MethodType

if __package__:
    from .joint_startup import replace_attribute
    from .ps_exit_trace import Trace, observe_close, install_child
    from .ps_exit_finalizing import attach
    from .joint_exit_guard import verify_package, write_new
else:
    from joint_startup import replace_attribute
    from ps_exit_trace import Trace, observe_close, install_child
    from ps_exit_finalizing import attach
    from joint_exit_guard import verify_package, write_new


def describe(exc):
    return dict(type=type(exc).__name__, message=str(exc))


def cache_exit(record):
    try:
        bridge = record['bridge']
        process = bridge._worker
        pid, code = process.pid, process.exitcode
        info = bridge.info()
        record.update(pid=pid, exitcode=code, info=info,
            exited=bool(type(pid) is int and type(code) is int and not process.is_alive()
                        and info.get('cleanup_complete') is True))
    except BaseException as exc:
        record['observation_errors'].append(describe(exc))


def capture_bridge(bridge_type, records, exits):
    def construct(*args, **kwargs):
        bridge = bridge_type.__new__(bridge_type)
        record = dict(bridge=bridge, trace=None, pid=None, exitcode=None, exited=False, info=None,
            close_thread_name=None, close_thread_ident=None, constructor_error=None, observation_errors=[])
        records.append(record)
        original_close = bridge_type.close
        def closing(self, *a, **k):
            # The normal joint call is on the processing thread, not the
            # owner's main thread. Bind lazily to the actual first caller.
            if record['trace'] is None:
                try:
                    record['trace'] = Trace(exits, 'parent')
                    record['close_thread_name'] = threading.current_thread().name
                    record['close_thread_ident'] = threading.get_ident()
                except BaseException as exc:
                    record['observation_errors'].append(describe(exc))
            try:
                if record['trace'] is None:
                    return original_close(self, *a, **k)
                return observe_close(original_close, self, record['trace'], *a, **k)
            finally:
                cache_exit(record)
        try:
            bridge.close = MethodType(closing, bridge)
        except BaseException as exc:
            record['observation_errors'].append(describe(exc))
        try:
            bridge_type.__init__(bridge, *args, **kwargs)
            return bridge
        except BaseException as exc:
            record['constructor_error'] = describe(exc)
            raise
    return construct


def ps_worker(connection, backend_source, *, root, source, exits, states, host_check=False):
    delegated, hooks = False, None
    try:
        verify_package(root)
        if __package__:
            from .lean_ps_worker import ps_worker as original
        else:
            from lean_ps_worker import ps_worker as original
        trace = attach(Trace(exits, 'child'), states)
        hooks = install_child(trace)
        success = False
        try:
            delegated = True
            result = original(connection, backend_source, root=root, source=source, host_check=host_check)
            success = True
            return result
        finally:
            hooks.after_delegate(success=success)
    except BaseException as exc:
        if delegated:
            raise
        if hooks is not None:
            hooks.restore()
        try:
            connection.send((0, 'error', type(exc).__name__+': '+str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
        finally:
            connection.close()


def owner_worker(*args, root, source, exits, states):
    if __package__:
        from . import lean_ps_worker as lean, joint_startup
    else:
        import lean_ps_worker as lean, joint_startup
    verify_package(root)
    records, errors = [], []
    guard = joint_startup.guard_session
    failure = None
    with ExitStack() as stack:
        def guarded(session, trace):
            result = guard(session, trace)
            try:
                module = sys.modules[type(session).__module__]
                bridge_type = module.Bridge25
                stack.enter_context(replace_attribute(module, 'Bridge25', capture_bridge(bridge_type, records, exits)))
            except BaseException as exc:
                errors.append(describe(exc))
            return result
        stack.enter_context(replace_attribute(joint_startup, 'guard_session', guarded))
        stack.enter_context(replace_attribute(lean, 'ps_worker', partial(ps_worker, exits=exits, states=states)))
        try:
            return lean.owner_worker(*args, root=root, source=source)
        except BaseException as exc:
            failure = describe(exc)
            raise
        finally:
            report = dict(schema='v3b25_joint_exit_owner_v1', owner_pid=os.getpid(), original_error=failure,
                observation_errors=errors, bridges=[{k:v for k,v in r.items() if k not in ('bridge','trace')} for r in records])
            try:
                write_new(Path(args[1])/'owner_joint_exit.json', report)
            except BaseException as exc:
                print('附加退出报告未导出，保留原异常/目录：'+str(exc), flush=True)


def start_owner(context, *args, root, source, exits, states, owners):
    child = context.Process(target=partial(owner_worker, root=root, source=source, exits=exits, states=states),
        args=args, name='joint25-lean-exit60-owner', daemon=False)
    record = dict(process=child, pid=None, directory=str(args[1]))
    owners.append(record)
    child.start()
    record['pid'] = child.pid
    return child
