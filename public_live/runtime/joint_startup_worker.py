"""One-shot startup instrumentation around the unchanged shared-owner lifecycle."""
from pathlib import Path
import sys

if __package__:
    from .joint_startup import StartupTrace,instrument_binding
else:
    from joint_startup import StartupTrace,instrument_binding


def timed_owner_main(binding,trace,owner_main,owner_module,*args,release_contract=None):
    # Resolve here, inside the inherited GC/entry contexts, not during cold import.
    deps=trace.call('owner_dependencies',owner_module._dependencies)
    bootstrap,stop=deps.bootstrap,deps.stop
    deps.bootstrap=lambda *a,**k:trace.call('algorithm_bootstrap',lambda:bootstrap(*a,**k))
    deps.stop=lambda *a,**k:trace.call('heart_stop',lambda:stop(*a,**k),cancellable=False)
    return owner_main(binding,*args,dependencies=deps)


def finish_worker(root,directory,binding,trace,failure,original):
    try:
        if binding is not None:
            trace.call('postrun_reports',lambda:original.finish_reports(root,directory,binding,failure=failure),cancellable=False)
    finally:
        try:trace.finish(wrapper_error=failure,
            retention_reasons=original.retention_reasons(binding) if binding is not None else [])
        finally:
            if binding is not None:original.retain_if_unsafe(binding)


def worker(base,directory,mailbox,stop,metrics_ready,*,release_contract=None):
    root=Path(__file__).resolve().parent;binding=None;failure=None
    trace=StartupTrace(directory,stop)
    if __package__:
        from . import joint_concurrent_worker as original
    else:
        import joint_concurrent_worker as original
    try:
        from joint_startup_guard import verify_startup
        if release_contract is None:
            trace.call('package_checks',lambda:verify_startup(root))
        else:
            from public_live_identity import check_runtime
            trace.call('package_checks',lambda:check_runtime(root,release_contract))
        frozen=root/'frozen'
        if str(frozen) not in sys.path:sys.path.insert(0,str(frozen))
        def activate_frozen():
            if release_contract is not None:
                from public_live_contract import activate_runtime
                return activate_runtime(release_contract)
            from entry25_guard import validate,activate
            validate(frozen);activate(frozen)
        trace.call('frozen_activate',activate_frozen)
        def imports():
            from joint_concurrent_binding import ConcurrentBinding
            import joint_concurrent_owner
            from joint_heart_worker import install_binding
            from effective25 import owner as inherited_owner
            import run_entry25_live as inherited
            return ConcurrentBinding,joint_concurrent_owner,install_binding,inherited_owner,inherited
        Binding,owner,install_binding,inherited_owner,inherited=trace.call('runtime_imports',imports)
        binding=instrument_binding(Binding(root),trace)
        def main(*args):return timed_owner_main(binding,trace,owner.owner_main,owner,*args,
                                               release_contract=release_contract)
        with install_binding(binding,release_contract=release_contract),original.install_owner_main(inherited_owner,main):
            if release_contract is None:
                inherited.entry_owner(base,directory,mailbox,stop,metrics_ready)
            else:
                from public_live_gc_owner import run_owner
                run_owner(base,directory,mailbox,stop,metrics_ready,
                          release_contract=release_contract)
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc));raise
    finally:finish_worker(root,directory,binding,trace,failure,original)


def start_owner(context,base,directory,mailbox,stop,metrics_ready):
    process=context.Process(target=worker,args=(base,directory,mailbox,stop,metrics_ready),
        name='joint-effective25-startup-fivefps-owner',daemon=False)
    process.start();return process
