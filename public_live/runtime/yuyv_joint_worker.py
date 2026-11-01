"""Child-only composition around the frozen snapshot/GC/retention lifecycle."""
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from .yuyv_joint_guard import verify_package, write_new
    from .joint_startup import replace_attribute
else:
    from yuyv_joint_guard import verify_package, write_new
    from joint_startup import replace_attribute


@contextmanager
def install_runtime():
    if __package__:
        from . import joint_concurrent_binding as binding, joint_concurrent_worker as concurrent, joint_shared_video as shared
        from .yuyv_joint_binding import YuyvJointBinding, SharedYuyvResources
    else:
        import joint_concurrent_binding as binding, joint_concurrent_worker as concurrent, joint_shared_video as shared
        from yuyv_joint_binding import YuyvJointBinding, SharedYuyvResources
    original = concurrent.finish_reports
    def finish(root, directory, actual, **kwargs):
        error = None
        try: return original(root, directory, actual, verify=verify_package, **kwargs)
        except BaseException as exc: error = exc; raise
        finally:
            try: write_new(Path(directory) / 'yuyv_iic_owner.json', actual.native_report())
            except BaseException as exc:
                if error is None: raise
                print('保留原报告错误；YUYV/IIC导出另有错误：' + str(exc), flush=True)
    with replace_attribute(binding, 'ConcurrentBinding', YuyvJointBinding), \
            replace_attribute(shared, 'SharedVideoResources', SharedYuyvResources), \
            replace_attribute(concurrent, 'finish_reports', finish):
        yield


def worker(base, directory, mailbox, stop, metrics_ready):
    verify_package(Path(__file__).resolve().parent)
    if __package__: from . import joint_snapshot_worker as original
    else: import joint_snapshot_worker as original
    with install_runtime(): original.worker(base, directory, mailbox, stop, metrics_ready)


def start_owner(context, base, directory, mailbox, stop, metrics_ready):
    child = context.Process(target=worker, args=(base, directory, mailbox, stop, metrics_ready),
        name='joint25-yuyv-pl-video-owner', daemon=False)
    child.start()
    return child
