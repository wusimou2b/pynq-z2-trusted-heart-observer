"""Use the qualified PS codec and scalar-state codec in the actual live owner."""
from contextlib import contextmanager, ExitStack
from functools import partial
from state_wire_live_guard import verify_new as verify

ORIGINAL = '73bb34fce0a6fc178fdc34ba43229c9ded4cbb46cf3525bb37c8416f8f422d74'


def verified_ps(connection, backend_source, *, root, expected, **kwargs):
    verify(root, expected)
    from ps_wire_live_runtime import verified_ps as retained
    return retained(connection, backend_source, root=root, expected=ORIGINAL, **kwargs)


def require_channel(spec, channel):
    from video_state_binary import StateChannel
    if type(channel) is not StateChannel:
        raise RuntimeError('verified live scalar codec not installed')
    if (channel.run_epoch, channel.manifest_sha256) != (spec['run_epoch'], spec['manifest_sha256']):
        raise RuntimeError('live scalar channel identity differs')


def video_child(spec, *args, expected):
    verify(spec['root'], expected)
    if not args:
        raise RuntimeError('live scalar channel missing')
    require_channel(spec, args[0])
    from ps_wire_live_runtime import video_child as retained
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
    stages = make_shared()
    process = context.Process(target=partial(owner_worker, root=root, expected=expected,
        exit_stages=stages, **kwargs), args=args, name='joint25-state-wire-owner', daemon=False)
    process.start()
    return process


@contextmanager
def parent_scope(root, expected):
    verify(root, expected)
    from joint_startup import replace_attribute
    import video_split_runtime
    with replace_attribute(video_split_runtime, 'start_owner', partial(start_owner, expected=expected)):
        yield


@contextmanager
def installed(root, expected, *, exit_stages=None):
    verify(root, expected)
    from ps_wire_live_runtime import installed as retained
    from joint_startup import replace_attribute
    with retained(root, ORIGINAL, exit_stages=exit_stages) as libraries, ExitStack() as stack:
        import compact_video_runtime, compact_video_process
        from video_state_binary import StateChannel
        stack.enter_context(replace_attribute(compact_video_runtime, 'StateChannel', StateChannel))
        stack.enter_context(replace_attribute(compact_video_runtime, 'verified_heart_entry',
            partial(verified_ps, expected=expected, exit_stages=exit_stages)))
        stack.enter_context(replace_attribute(compact_video_process, 'run_child',
            partial(video_child, expected=expected)))
        yield libraries
