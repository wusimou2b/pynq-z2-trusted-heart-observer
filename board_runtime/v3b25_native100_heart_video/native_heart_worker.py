"""Native statistics only in the original spawned, hardware-free PS worker."""
from contextlib import contextmanager
import os
from pathlib import Path
import sys

if __package__:
    from .joint_startup import replace_attribute
else:
    from joint_startup import replace_attribute

ROOT=Path(__file__).resolve().parent


def ps_worker(connection,source):
    delegated=False
    try:
        if source not in ('python_fixed','pl_mmio'):raise ValueError('native worker backend source invalid')
        if __package__:
            from .native_heart_prepare import validate_prepared
            from .statistics25_native import load_native,make_candidate
            from .ps_budget_runtime import load_runtime,no_hardware
        else:
            from native_heart_prepare import validate_prepared
            from statistics25_native import load_native,make_candidate
            from ps_budget_runtime import load_runtime,no_hardware
        with no_hardware():
            prepared=validate_prepared(ROOT,hardware=source=='pl_mmio')
            deps=load_runtime(ROOT/'frozen')
            import entry25_candidate as candidate
            from entry25_worker import ReadyIdentity
            core=load_native(prepared['binary']);api=make_candidate(core)
            metadata=dict(native_statistics=dict(loaded=True,implementation=core.implementation,
                binary_sha256=prepared['binary']['sha256'],c_sha256=prepared['c_sha256'],
                native_manifest_sha256=prepared['native_manifest_sha256'],
                preparation_sha256=prepared['preparation_sha256'],ps_pid=os.getpid()))
            with replace_attribute(candidate,'DelayedPeakChain',api.Chain):
                delegated=True
                deps.worker(ReadyIdentity(connection,metadata),source)
    except BaseException as exc:
        if not delegated:
            try:connection.send((0,'error',type(exc).__name__+': '+str(exc)))
            except (BrokenPipeError,EOFError,OSError):pass
        else:raise
    finally:
        if not delegated:connection.close()


@contextmanager
def install_ps_entry(root):
    """Owner-local selection, before original entry_owner imports its PS target."""
    frozen=str(Path(root).resolve()/'frozen');added=frozen not in sys.path
    if added:sys.path.insert(0,frozen)
    try:
        import entry25_worker
        with replace_attribute(entry25_worker,'worker',ps_worker):yield
    finally:
        if added:sys.path.remove(frozen)


def worker(base,directory,mailbox,stop,metrics_ready):
    if __package__:
        from . import browser_heart_worker as original
        from .native_heart_guard import verify_package
    else:
        import browser_heart_worker as original
        from native_heart_guard import verify_package
    verify_package(ROOT)
    with install_ps_entry(ROOT),replace_attribute(original,'verify_package',verify_package):
        original.worker(base,directory,mailbox,stop,metrics_ready)


def start_owner(context,*args):
    child=context.Process(target=worker,args=args,name='joint25-native100-browser-owner',daemon=False)
    child.start()
    return child
