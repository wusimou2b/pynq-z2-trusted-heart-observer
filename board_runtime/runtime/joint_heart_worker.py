"""Preserve frozen entry/GC/PS-worker chain; replace only board.prepare."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True


@contextmanager
def install_binding(binding):
    from effective25 import identity
    original_bootstrap=identity.bootstrap
    board=original_prepare=None
    def bootstrap(*args,**kwargs):
        nonlocal board,original_prepare
        result=original_bootstrap(*args,**kwargs)
        if kwargs.get("algorithm") and board is None:
            from effective25 import board as loaded
            board=loaded
            original_prepare=board.prepare
            board.prepare=binding.prepare
        return result
    identity.bootstrap=bootstrap
    try:
        yield
    finally:
        identity.bootstrap=original_bootstrap
        if board is not None:
            board.prepare=original_prepare


def worker(base,directory,mailbox,stop,metrics_ready):
    root=Path(__file__).resolve().parent
    from joint_heart_guard import verify_package,write_new
    verify_package(root)
    frozen=root/"frozen"
    if str(frozen) not in sys.path:
        sys.path.insert(0,str(frozen))
    from entry25_guard import validate,activate
    validate(frozen); activate(frozen)
    from joint_heart_binding import JointBinding
    import run_entry25_live as inherited
    binding=JointBinding(root)
    failure=None
    try:
        with install_binding(binding):
            # The unchanged function installs candidate worker, original GC
            # observer/window and original hardware owner in the same order.
            inherited.entry_owner(base,directory,mailbox,stop,metrics_ready)
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        owner_path=Path(directory)/"owner_result.json"
        owner=json.loads(owner_path.read_text(encoding="utf-8")) if owner_path.is_file() else {}
        # No unconditional owner.close here: the inherited session might still
        # be live/incompletely drained. Only Session25's release delegates close.
        write_new(Path(directory)/"joint_owner_result.json",dict(
            schema="v3b25_joint_heart_owner_v1",owner_pid=os.getpid(),parent_pid=os.getppid(),
            binding_installed=binding.prepare_calls==1,wrapper_error=failure,
            inherited_cleanup_complete=owner.get("cleanup_complete",False),**binding.report()))


def start_owner(context,base,directory,mailbox,stop,metrics_ready):
    process=context.Process(target=worker,args=(base,directory,mailbox,stop,metrics_ready),
                            name="joint-effective25-heart-owner",daemon=False)
    process.start()
    return process
