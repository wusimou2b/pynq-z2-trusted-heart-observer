"""Overlap the original pure-PS constructor with unchanged shared preparation."""
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from .joint_overlap import Warmup,ClaimTrace,install_session
    from .joint_startup import replace_attribute
else:
    from joint_overlap import Warmup,ClaimTrace,install_session
    from joint_startup import replace_attribute


def timed_owner_main(binding,trace,owner_main,owner_module,*args):
    warm=None
    try:
        deps=trace.call('owner_dependencies',owner_module._dependencies)
        bootstrap,prepare,stop=deps.bootstrap,deps.prepare,deps.stop
        def boot(*a,**k):
            nonlocal warm
            result=trace.call('algorithm_bootstrap',lambda:bootstrap(*a,**k))
            from effective25 import session as session_module
            from entry25_guard import identity
            if warm is not None:raise RuntimeError('algorithm bootstrap/PS warmup already attempted')
            warm=Warmup(session_module.Bridge25,trace,identity(binding.frozen))
            binding.overlap_warmup=warm
            trace.call('parallel_ps_launch',warm.start)
            return result
        def prepared(*a,**k):
            session=prepare(*a,**k)
            if warm is None:raise RuntimeError('PS warmup was not launched before preparation')
            from effective25 import session as session_module
            install_session(session,session_module,warm);return session
        deps.bootstrap=boot;deps.prepare=prepared
        deps.stop=lambda *a,**k:trace.call('heart_stop',lambda:stop(*a,**k),cancellable=False)
        return owner_main(binding,*args,dependencies=deps)
    finally:
        # Still inside the frozen entry/GC/worker-binding contexts. Disposal is
        # not conditional on a working trace or successful report publication.
        if warm is not None:warm.dispose(binding.session)
        if __package__:from .joint_heart_guard import write_new
        else:from joint_heart_guard import write_new
        report=warm.report() if warm is not None else dict(schema='v3b25_overlap_owner_v1',
            attempted=False,bridge_created=0,claims=0,error=dict(type='NotStarted',message='bootstrap未完成'),cleanup_complete=True)
        write_new(Path(args[1])/'owner_overlap.json',report)


@contextmanager
def install_runtime(verify):
    if __package__:
        from . import joint_startup as runtime,joint_startup_worker as startup,joint_startup_guard as guard
    else:
        import joint_startup as runtime,joint_startup_worker as startup,joint_startup_guard as guard
    original_guard=runtime.guard_session
    def guarded(session,trace):return original_guard(session,ClaimTrace(trace))
    with replace_attribute(runtime,'guard_session',guarded),replace_attribute(startup,'timed_owner_main',timed_owner_main),\
            replace_attribute(guard,'verify_startup',verify):yield


def worker(base,directory,mailbox,stop,metrics_ready):
    if __package__:
        from .joint_overlap_guard import verify_overlap
        from . import joint_startup_worker as original
    else:
        from joint_overlap_guard import verify_overlap
        import joint_startup_worker as original
    with install_runtime(verify_overlap):original.worker(base,directory,mailbox,stop,metrics_ready)


def start_owner(context,base,directory,mailbox,stop,metrics_ready):
    process=context.Process(target=worker,args=(base,directory,mailbox,stop,metrics_ready),
        name='joint-effective25-overlap-fivefps-owner',daemon=False)
    process.start();return process
