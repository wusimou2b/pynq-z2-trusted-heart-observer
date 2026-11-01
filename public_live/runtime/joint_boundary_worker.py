"""Compose the reviewed overlap worker; export only after original retention ends."""
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from .joint_startup import replace_attribute
    from .joint_boundary import Probe
else:
    from joint_startup import replace_attribute
    from joint_boundary import Probe

@contextmanager
def install_runtime(probe):
    if __package__:
        from . import joint_overlap_worker as overlap,joint_startup_worker as startup,joint_concurrent_worker as concurrent
        from .joint_heart_guard import write_new
    else:
        import joint_overlap_worker as overlap,joint_startup_worker as startup,joint_concurrent_worker as concurrent
        from joint_heart_guard import write_new
    timed,finish=overlap.timed_owner_main,startup.finish_worker
    def observed(binding,trace,owner_main,owner_module,*args):
        def main(binding,*a,dependencies):
            prepare=dependencies.prepare
            def prepared(*pa,**pk):
                session=prepare(*pa,**pk)
                try:probe.install(session,binding.video,a[2])
                except BaseException as exc:probe.install_error=dict(type=type(exc).__name__,message=str(exc))
                return session
            dependencies.prepare=prepared
            return owner_main(binding,*a,dependencies=dependencies)
        return timed(binding,trace,main,owner_module,*args)
    def finished(root,directory,binding,trace,failure,original):
        original_error=None
        try:return finish(root,directory,binding,trace,failure,original)
        except BaseException as exc:
            original_error=exc;raise
        finally:
            if binding is None or not concurrent.retention_reasons(binding):
                try:
                    probe.restore()
                    write_new(Path(directory)/'owner_boundaries.json',probe.report())
                except BaseException as exc:
                    probe.export_error=dict(type=type(exc).__name__,message=str(exc))
                    if original_error is None:raise
                    print('边界导出另有错误（原收尾错误保留）：'+str(probe.export_error),flush=True)
    with replace_attribute(overlap,'timed_owner_main',observed),replace_attribute(startup,'finish_worker',finished):yield

def worker(base,directory,mailbox,stop,metrics_ready):
    if __package__:
        from .joint_boundary_guard import verify_boundary
        from . import joint_overlap_worker as original
    else:
        from joint_boundary_guard import verify_boundary
        import joint_overlap_worker as original
    verify_boundary(Path(__file__).resolve().parent)
    probe=Probe()
    with install_runtime(probe):original.worker(base,directory,mailbox,stop,metrics_ready)

def start_owner(context,base,directory,mailbox,stop,metrics_ready):
    process=context.Process(target=worker,args=(base,directory,mailbox,stop,metrics_ready),
        name='joint-effective25-boundary-fivefps-owner',daemon=False)
    process.start();return process
