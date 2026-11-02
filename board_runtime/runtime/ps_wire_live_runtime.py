"""Flat IPC connected to the preserved real live owner and its exit observer."""
from contextlib import contextmanager, ExitStack
from functools import partial
from ps_wire_live_guard import verify_new as verify

ORIGINAL = '69fc0ed0eb25085cb5d61c2c590206e45173e82c126faa68d68557fd762b23eb'


def verified_ps(connection, backend_source, *, root, expected, **kwargs):
    verify(root, expected)
    from owner_flat_live_runtime import verified_ps as retained
    return retained(connection, backend_source, root=root, expected=ORIGINAL, **kwargs)


def video_child(spec, *args, expected):
    verify(spec['root'], expected)
    from owner_flat_live_runtime import video_child as retained
    return retained(spec, *args, expected=ORIGINAL)


def owner_worker(*args, root, expected, exit_stages, **kwargs):
    verify(root, expected)
    from main_ps_exit_worker import defer_offline_pandas
    with defer_offline_pandas(root), installed(root, expected, exit_stages=exit_stages):
        from compact_video_runtime import worker
        return worker(*args, root=root, **kwargs)


def start_owner(context, *args, root, expected, **kwargs):
    verify(root, expected)
    from lean_ps_exit_trace import make_shared
    stages=make_shared()
    process=context.Process(target=partial(owner_worker,root=root,expected=expected,
        exit_stages=stages,**kwargs),args=args,name='joint25-live-flat-ipc-owner',daemon=False)
    process.start();return process


@contextmanager
def parent_scope(root, expected):
    verify(root, expected)
    from joint_startup import replace_attribute
    import video_split_runtime
    with replace_attribute(video_split_runtime,'start_owner',partial(start_owner,expected=expected)):
        yield


@contextmanager
def installed(root, expected, *, exit_stages=None):
    verify(root, expected)
    from ps_live_wire_scope import installed as flat, require_installed
    from owner_flat_live_runtime import installed as retained
    from joint_startup import replace_attribute
    # Enter BEFORE retained imports its Bridge factory. It keeps its own exit
    # observer, transaction scheduling, copy adapters and original owner loop.
    with flat(), retained(root, ORIGINAL, exit_stages=exit_stages) as libraries, ExitStack() as stack:
        import main_heart_process, compact_video_runtime, compact_video_process
        original_bridge=main_heart_process.Bridge
        def bridge(*args, **kwargs):
            result=original_bridge(*args, **kwargs)
            try:require_installed(result)
            except BaseException:
                result.close();raise
            return result
        stack.enter_context(replace_attribute(main_heart_process,'Bridge',bridge))
        stack.enter_context(replace_attribute(compact_video_runtime,'verified_heart_entry',
            partial(verified_ps,expected=expected,exit_stages=exit_stages)))
        stack.enter_context(replace_attribute(compact_video_process,'run_child',
            partial(video_child,expected=expected)))
        yield libraries
