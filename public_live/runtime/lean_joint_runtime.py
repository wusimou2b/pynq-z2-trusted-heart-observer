"""Live entry using the saved1071-qualified scopes; original DMA teardown."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager, ExitStack
from functools import partial
import json
from pathlib import Path
import sys

def check(root, expected, *, release_contract=None):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    from lean_joint_guard import verify
    return verify(root, expected) if release_contract is None else verify_boundary(root, release_contract)

def exit_report(stages, libraries):
    from lean_ps_exit_trace import snapshot, analyze
    doc = {side: analyze(snapshot(stages, side)) for side in ('parent', 'child')}
    doc['owner_pandas_loaded_at_end'] = 'pandas' in sys.modules
    doc['native_receipts'] = [dict(failure=lib.failure, first_sample=lib.entry_trace_report(), live_binding=getattr(lib, 'binding_info', None)) for lib in libraries]
    return doc

def verified_ps(connection, backend_source, *, root, lean_sha256, exit_stages, delegate, manifest_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        lean_sha256 = release_contract['expected_manifest_sha256']
    check(root, lean_sha256, release_contract=release_contract)
    from lean_ps_exit_trace import Trace, install_child
    from main_ps_exit_worker import defer_offline_pandas
    hooks = install_child(Trace(exit_stages, 'child'))
    success = False
    try:
        with defer_offline_pandas(root):
            from compact_delivery_runtime import verified_ps as retained
            from lean_joint_guard import BASE
            result = retained(connection, backend_source, root=root, compact_sha256=BASE, delegate=delegate, manifest_sha256=manifest_sha256, **kwargs, release_contract=release_contract)
        success = True
        return result
    finally:
        hooks.after_delegate(success=success)

def owner_worker(*args, root, lean_sha256, exit_stages, release_contract=None, **kwargs):
    if release_contract is not None:
        lean_sha256 = release_contract['expected_manifest_sha256']
    check(root, lean_sha256, release_contract=release_contract)
    from main_ps_exit_worker import defer_offline_pandas
    with defer_offline_pandas(root), installed(root, lean_sha256, exit_stages=exit_stages, release_contract=release_contract):
        from compact_video_runtime import worker
        return worker(*args, root=root, **kwargs, release_contract=release_contract)

def start_owner(context, *args, root, lean_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        lean_sha256 = release_contract['expected_manifest_sha256']
    check(root, lean_sha256, release_contract=release_contract)
    from lean_ps_exit_trace import make_shared
    stages = make_shared()
    p = context.Process(target=partial(owner_worker, root=root, lean_sha256=lean_sha256, exit_stages=stages, **kwargs, release_contract=release_contract), args=args, name='joint25-lean-owner', daemon=False)
    p.start()
    return p

@contextmanager
def projected_snapshots():
    """Install projection after original SnapshotAdapter; restore in reverse."""
    from joint_startup import replace_attribute
    from joint_snapshot import SnapshotAdapter
    from owner_publish_projection import publication_projection
    original_install, original_restore = (SnapshotAdapter.install, SnapshotAdapter.restore)
    active = []

    def install(self, session):
        original_install(self, session)
        scope = publication_projection(session)
        try:
            scope.__enter__()
        except BaseException:
            original_restore(self)
            raise
        active.append((self, scope))

    def restore(self):
        for i, (adapter, scope) in enumerate(active):
            if adapter is self:
                active.pop(i)
                scope.__exit__(None, None, None)
                break
        return original_restore(self)
    with replace_attribute(SnapshotAdapter, 'install', install), replace_attribute(SnapshotAdapter, 'restore', restore):
        try:
            yield
        finally:
            for adapter, scope in reversed(active):
                scope.__exit__(None, None, None)
                original_restore(adapter)
            active.clear()

@contextmanager
def installed(root, expected, *, exit_stages=None, release_contract=None):
    if release_contract is not None:
        expected = release_contract['expected_manifest_sha256']
    check(root, expected, release_contract=release_contract)
    root = Path(root)
    from compact_delivery_runtime import installed as retained
    from lean_joint_guard import BASE
    from joint_startup import replace_attribute
    bridges = []
    libraries = []
    with retained(root, BASE, release_contract=release_contract), ExitStack() as stack:
        import main_heart_process, compact_video_runtime, video_split_runtime, main_heart_native_build, spatial_gil_worker
        from lean_ps_worker import load_original
        load_original(root / 'frozen', release_contract=release_contract)
        import evidence_reuse
        from ps_wire_candidate import Bridge
        from owner_display_copy import bulk_owner_writer
        from sample_entry_native import load
        from lean_native_binding import bind_registered
        from lean_ps_exit_trace import Trace, observe_close, snapshot, analyze
        build = json.loads((root / 'lean-joint-manifest.json').read_bytes())['native_build_sha256']

        def load_native(_, *, release_contract=release_contract):
            library = load(root, build, release_contract=release_contract)
            libraries.append(library)
            return library
        old_bind = spatial_gil_worker.load_candidate

        def bind_native(library):
            return bind_registered(library, libraries, old_bind)

        def bridge(source, target, *, run_id):
            if exit_stages is None:
                raise RuntimeError('PS bridge must be created in owning process')
            b = Bridge(source, target, run_id=run_id)
            bridges.append(b)
            old = type(b).close
            b.close = lambda: observe_close(old, b, Trace(exit_stages, 'parent'))
            return b
        stack.enter_context(evidence_reuse.install_reuse())
        stack.enter_context(bulk_owner_writer())
        stack.enter_context(projected_snapshots())
        for obj, name, value in ((main_heart_process, 'Bridge', bridge), (compact_video_runtime, 'verified_heart_entry', partial(verified_ps, lean_sha256=expected, exit_stages=exit_stages, release_contract=release_contract)), (video_split_runtime, 'start_owner', partial(start_owner, lean_sha256=expected, release_contract=release_contract)), (spatial_gil_worker, 'load_candidate', bind_native), (main_heart_native_build, 'load_verified', load_native)):
            stack.enter_context(replace_attribute(obj, name, value))
        try:
            yield
        finally:
            if exit_stages is not None and bridges and all((not b._worker.is_alive() for b in bridges)):
                directory = root / 'continuous-results'
                if directory.is_dir():
                    doc = exit_report(exit_stages, libraries)
                    with (directory / 'lean-ps-exit-stages.json').open('x', encoding='utf-8') as f:
                        json.dump(doc, f, indent=2)
