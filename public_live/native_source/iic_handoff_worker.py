"""Spawn-safe IIC composition, unchanged snapshot/GC/cancel/retention lifecycle."""
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from .iic_handoff_guard import verify_package
    from .iic_handoff_binding import HandoffBinding
    from .joint_startup import replace_attribute
else:
    from iic_handoff_guard import verify_package
    from iic_handoff_binding import HandoffBinding
    from joint_startup import replace_attribute


@contextmanager
def install_runtime():
    if __package__: from . import yuyv_joint_binding as binding, yuyv_joint_worker as previous
    else: import yuyv_joint_binding as binding, yuyv_joint_worker as previous
    with replace_attribute(binding, 'YuyvJointBinding', HandoffBinding), \
            replace_attribute(previous, 'verify_package', verify_package), previous.install_runtime():
        yield


def worker(base, directory, mailbox, stop, metrics_ready):
    verify_package(Path(__file__).resolve().parent)
    if __package__: from . import joint_snapshot_worker as original
    else: import joint_snapshot_worker as original
    with install_runtime(): original.worker(base, directory, mailbox, stop, metrics_ready)


def start_owner(context, base, directory, mailbox, stop, metrics_ready):
    child = context.Process(target=worker, args=(base, directory, mailbox, stop, metrics_ready),
        name='joint25-complete-iic-yuyv-owner', daemon=False)
    child.start(); return child
