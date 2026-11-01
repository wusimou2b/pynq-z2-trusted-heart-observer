"""Use original sequential startup/GC/owner, without per-sample probes."""
from contextlib import contextmanager
import json
from pathlib import Path

if __package__:
    from .joint_startup import replace_attribute
else:
    from joint_startup import replace_attribute


def verify_package(root):
    if __package__: from .heart_video_guard import verify_package as verify
    else: from heart_video_guard import verify_package as verify
    return verify(root)


@contextmanager
def install_runtime(*, release_contract=None):
    if __package__:
        from . import joint_concurrent_binding as binding, joint_shared_video as shared
        from . import joint_startup_guard as guard, joint_concurrent_worker as concurrent
        from .heart_video_binding import SnapshotVideoBinding, finish_snapshot
        from .yuyv_joint_binding import SharedYuyvResources
    else:
        import joint_concurrent_binding as binding, joint_shared_video as shared
        import joint_startup_guard as guard, joint_concurrent_worker as concurrent
        from heart_video_binding import SnapshotVideoBinding, finish_snapshot
        from yuyv_joint_binding import SharedYuyvResources
    original = concurrent.finish_reports
    def checked(root):
        if release_contract is None:
            return verify_package(root)
        from public_live_lower_identity import verify_boundary
        return verify_boundary(root, release_contract)
    def finish(root, directory, actual, **kwargs):
        owner_path = Path(directory)/'owner_result.json'
        owner = json.loads(owner_path.read_text('utf-8')) if owner_path.is_file() else {}
        finish_snapshot(actual, owner)
        return original(root, directory, actual, verify=checked, **kwargs)
    if release_contract is not None:
        with replace_attribute(binding, 'ConcurrentBinding', SnapshotVideoBinding), \
             replace_attribute(shared, 'SharedVideoResources', SharedYuyvResources), \
             replace_attribute(concurrent, 'finish_reports', finish):
            yield
        return
    with replace_attribute(binding, 'ConcurrentBinding', SnapshotVideoBinding), \
            replace_attribute(shared, 'SharedVideoResources', SharedYuyvResources), \
            replace_attribute(guard, 'verify_startup', verify_package), \
            replace_attribute(concurrent, 'finish_reports', finish):
        yield


def worker(base, directory, mailbox, stop, metrics_ready, *, release_contract=None):
    if __package__: from . import joint_startup_worker as original
    else: import joint_startup_worker as original
    with install_runtime(release_contract=release_contract):
        original.worker(base, directory, mailbox, stop, metrics_ready,
                        release_contract=release_contract)


def start_owner(context, base, directory, mailbox, stop, metrics_ready):
    child = context.Process(target=worker, args=(base, directory, mailbox, stop, metrics_ready),
        name='joint25-heart-snapshot-pl-video-owner', daemon=False)
    child.start()
    return child
