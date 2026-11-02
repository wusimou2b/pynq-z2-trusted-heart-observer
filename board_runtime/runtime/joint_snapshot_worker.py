"""Use the exact boundary worker with a scoped single-construction Probe."""
from pathlib import Path
if __package__:
    from .joint_startup import replace_attribute
    from .joint_snapshot import SnapshotProbe
    from .joint_snapshot_guard import verify_snapshot
else:
    from joint_startup import replace_attribute
    from joint_snapshot import SnapshotProbe
    from joint_snapshot_guard import verify_snapshot


def worker(base,directory,mailbox,stop,metrics_ready):
    if __package__:
        from . import joint_boundary_worker as original
    else:
        import joint_boundary_worker as original
    verify_snapshot(Path(__file__).resolve().parent)
    with replace_attribute(original,'Probe',SnapshotProbe):
        original.worker(base,directory,mailbox,stop,metrics_ready)


def start_owner(context,base,directory,mailbox,stop,metrics_ready):
    process=context.Process(target=worker,args=(base,directory,mailbox,stop,metrics_ready),
        name='joint-effective25-snapshot-fivefps-owner',daemon=False)
    process.start()
    return process
