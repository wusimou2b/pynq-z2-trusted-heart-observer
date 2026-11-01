"""Flat IPC connected to the preserved real live owner and its exit observer."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager, ExitStack
from functools import partial
from ps_wire_live_guard import verify_new as verify
ORIGINAL = '18d8c48def3a89dd708e376b375273576430fc9126329371179a6212d44009cf'

def verified_ps(connection, backend_source, *, root, expected, release_contract=None, **kwargs):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(root, expected) if release_contract is None else verify_boundary(root, release_contract)
    from owner_flat_live_runtime import verified_ps as retained
    return retained(connection, backend_source, root=root, expected=ORIGINAL, **kwargs, release_contract=release_contract)

def video_child(spec, *args, expected, release_contract=None):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(spec['root'], expected) if release_contract is None else verify_boundary(spec['root'], release_contract)
    from owner_flat_live_runtime import video_child as retained
    return retained(spec, *args, expected=ORIGINAL, release_contract=release_contract)

def owner_worker(*args, root, expected, exit_stages, release_contract=None, **kwargs):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(root, expected) if release_contract is None else verify_boundary(root, release_contract)
    from main_ps_exit_worker import defer_offline_pandas
    with defer_offline_pandas(root), installed(root, expected, exit_stages=exit_stages, release_contract=release_contract):
        from compact_video_runtime import worker
        return worker(*args, root=root, **kwargs, release_contract=release_contract)

def start_owner(context, *args, root, expected, release_contract=None, **kwargs):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(root, expected) if release_contract is None else verify_boundary(root, release_contract)
    from lean_ps_exit_trace import make_shared
    stages = make_shared()
    process = context.Process(target=partial(owner_worker, root=root, expected=expected, exit_stages=stages, **kwargs, release_contract=release_contract), args=args, name='joint25-live-flat-ipc-owner', daemon=False)
    process.start()
    return process

@contextmanager
def parent_scope(root, expected, *, release_contract=None):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(root, expected) if release_contract is None else verify_boundary(root, release_contract)
    from joint_startup import replace_attribute
    import video_split_runtime
    with replace_attribute(video_split_runtime, 'start_owner', partial(start_owner, expected=expected, release_contract=release_contract)):
        yield

@contextmanager
def installed(root, expected, *, exit_stages=None, release_contract=None):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(root, expected) if release_contract is None else verify_boundary(root, release_contract)
    from ps_live_wire_scope import installed as flat, require_installed
    from owner_flat_live_runtime import installed as retained
    from joint_startup import replace_attribute
    with flat(), retained(root, ORIGINAL, exit_stages=exit_stages, release_contract=release_contract) as libraries, ExitStack() as stack:
        import main_heart_process, compact_video_runtime, compact_video_process
        original_bridge = main_heart_process.Bridge

        def bridge(*args, **kwargs):
            result = original_bridge(*args, **kwargs)
            try:
                require_installed(result)
            except BaseException:
                result.close()
                raise
            return result
        stack.enter_context(replace_attribute(main_heart_process, 'Bridge', bridge))
        stack.enter_context(replace_attribute(compact_video_runtime, 'verified_heart_entry', partial(verified_ps, expected=expected, exit_stages=exit_stages, release_contract=release_contract)))
        stack.enter_context(replace_attribute(compact_video_process, 'run_child', partial(video_child, expected=expected)))
        yield libraries
