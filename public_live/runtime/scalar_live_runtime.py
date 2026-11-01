"""Connect the qualified native scope to the actual live owner, not a replay."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager, ExitStack
from functools import partial
import json
from pathlib import Path
from scalar_live_guard import verify, BASE

def verified_ps(connection, backend_source, *, root, expected, exit_stages, delegate, manifest_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(root, expected) if release_contract is None else verify_boundary(root, release_contract)
    from lean_joint_runtime import verified_ps as retained
    from main_ps_exit_worker import defer_offline_pandas
    from scalar_result_scope import child_copies
    with defer_offline_pandas(root), child_copies():
        return retained(connection, backend_source, root=root, lean_sha256=BASE, exit_stages=exit_stages, delegate=delegate, manifest_sha256=manifest_sha256, **kwargs, release_contract=release_contract)

def video_child(spec, *args, expected, release_contract=None):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    verify(spec['root'], expected) if release_contract is None else verify_boundary(spec['root'], release_contract)
    from compact_delivery_runtime import video_child as retained
    selected = spec if release_contract is None else dict(spec, release_contract=release_contract)
    return retained(selected, *args)

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
    process = context.Process(target=partial(owner_worker, root=root, expected=expected, exit_stages=stages, **kwargs, release_contract=release_contract), args=args, name='joint25-scalar-owner', daemon=False)
    process.start()
    return process

@contextmanager
def parent_scope(root, expected, *, release_contract=None):
    """Notebook only installs the spawn target; no PS calculation bootstrap."""
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
    root = Path(root)
    from lean_joint_runtime import installed as retained
    from joint_startup import replace_attribute
    libraries = []
    with retained(root, BASE, exit_stages=exit_stages, release_contract=release_contract), ExitStack() as stack:
        import spatial_gil_worker, compact_video_runtime, compact_video_process
        from transaction_schedule import install
        import status60_ab_runtime
        from scalar_result_scope import owner_copies
        from lean_stop_handoff import owner_main
        previous_bind = status60_ab_runtime.Activation.bind

        def bind_session(registry, session):
            previous_bind(registry, session)
            session._scalar_copies = registry.stack.enter_context(owner_copies(session))
        stack.enter_context(replace_attribute(status60_ab_runtime.Activation, 'bind', bind_session))
        stack.enter_context(replace_attribute(compact_video_runtime, 'owner_main', owner_main))
        original_bind = spatial_gil_worker.load_candidate

        def bind(library):
            value = original_bind(library)
            result = install(value, root, release_contract=release_contract)
            libraries.append(result)
            return result
        stack.enter_context(replace_attribute(spatial_gil_worker, 'load_candidate', bind))
        stack.enter_context(replace_attribute(compact_video_runtime, 'verified_heart_entry', partial(verified_ps, expected=expected, exit_stages=exit_stages, release_contract=release_contract)))
        stack.enter_context(replace_attribute(compact_video_process, 'run_child', partial(video_child, expected=expected)))
        try:
            yield libraries
        finally:
            directory = root / 'continuous-results'
            if directory.is_dir() and libraries:
                reports = [lib.schedule_report() for lib in libraries]
                with (directory / 'transaction-schedule.json').open('x', encoding='utf-8') as f:
                    json.dump(dict(schema='scalar_live_transactions_v1', libraries=reports, calls=sum((r['calls'] for r in reports)), all_restored=all((r['all_restored'] for r in reports)), original_deadlines_unchanged=True), f, indent=2)
