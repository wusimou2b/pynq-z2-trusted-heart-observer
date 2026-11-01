"""Original PS imports plus the same Native100 class; no offline bootstrap."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager
from functools import partial
import os
from pathlib import Path
import sys
from types import SimpleNamespace
FORBIDDEN = {'pynq', 'cv2', 'smbus', 'smbus2', 'spidev'}
UNNEEDED = ('ps_budget_runtime', 'cProfile', 'pstats', 'display25', 'pilot25.board', 'heart_v3a.live.board', 'heart_v3a.live.session', 'v3a_25hz_live.session')

@contextmanager
def no_hardware():
    if any((n.split('.')[0] in FORBIDDEN for n in sys.modules)):
        raise RuntimeError('hardware module already imported in lean PS')

    class Block:

        def find_spec(self, fullname, path=None, target=None):
            if fullname.split('.')[0] in FORBIDDEN:
                raise RuntimeError('hardware import forbidden: ' + fullname)
    block = Block()
    sys.meta_path.insert(0, block)
    try:
        yield
    finally:
        sys.meta_path.remove(block)

def load_original(frozen, *, release_contract=None):
    """Validate the frozen package, then import only the original PS target."""
    frozen = Path(frozen).resolve()
    if str(frozen) not in sys.path:
        sys.path.insert(0, str(frozen))
    if release_contract is None:
        import entry25_guard
        if Path(entry25_guard.__file__).resolve() != frozen / 'entry25_guard.py':
            raise RuntimeError('mixed lean PS entry guard')
        entry25_guard.validate(frozen)
        entry25_guard.activate(frozen)
    else:
        from public_live_contract import activate_runtime
        context = activate_runtime(release_contract)
        if frozen != Path(context['runtime_root']) / 'frozen':
            raise ValueError('public frozen source differs from verified release')
    paths = (frozen / 'base/deps', frozen / 'base/deps/static', frozen / 'base/deps/static/checked', frozen / 'base/deps/static/checked/base')
    for path in reversed(paths):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    import entry25_candidate as candidate
    from entry25_worker import worker, ReadyIdentity
    return SimpleNamespace(candidate=candidate, worker=worker, ReadyIdentity=ReadyIdentity)

def import_identity():
    return dict(mode='entry25_original_imports_v1', unexpected_modules=sorted((n for n in sys.modules if any((n == p or n.startswith(p + '.') for p in UNNEEDED)))), hardware_imported=any((n.split('.')[0] in FORBIDDEN for n in sys.modules)))

class ReadyConnection:

    def __init__(self, connection):
        self.connection = connection

    def send(self, message):
        if message[:2] == (0, 'ready'):
            message = (0, 'ready', dict(message[2], lean_ps=import_identity()))
        return self.connection.send(message)

    def recv(self):
        return self.connection.recv()

    def poll(self, timeout):
        return self.connection.poll(timeout)

    def close(self):
        return self.connection.close()

def ps_worker(connection, backend_source, *, root, source, host_check=False, release_contract=None):
    if release_contract is not None:
        raise ValueError('public LIVE uses the explicit main_heart_process PS target')
    delegated = False
    try:
        if backend_source not in ('python_fixed', 'pl_mmio'):
            raise ValueError('lean PS backend source invalid')
        if host_check and backend_source != 'python_fixed':
            raise ValueError('host check cannot authorize physical PL')
        if __package__:
            from .lean_ps_guard import verify_source
            from .statistics25_native import load_native, make_candidate
            from .joint_startup import replace_attribute
        else:
            from lean_ps_guard import verify_source
            from statistics25_native import load_native, make_candidate
            from joint_startup import replace_attribute
        with no_hardware():
            prepared = verify_source(root, source, hardware=backend_source == 'pl_mmio', host_check=host_check) if release_contract is None else public_prepared(root, release_contract, hardware=backend_source == 'pl_mmio', host_check=host_check)
            deps = load_original(Path(root) / 'frozen', release_contract=release_contract)
            core = load_native(prepared['binary'], release_contract=release_contract)
            api = make_candidate(core)
            metadata = dict(native_statistics=dict(loaded=True, implementation=core.implementation, binary_sha256=prepared['binary']['sha256'], c_sha256=prepared['c_sha256'], native_manifest_sha256=prepared['native_manifest_sha256'], preparation_sha256=prepared['preparation_sha256'], ps_pid=os.getpid()))
            wrapped = deps.ReadyIdentity(ReadyConnection(connection), metadata)
            with replace_attribute(deps.candidate, 'DelayedPeakChain', api.Chain):
                delegated = True
                deps.worker(wrapped, backend_source)
    except BaseException as exc:
        if delegated:
            raise
        try:
            connection.send((0, 'error', type(exc).__name__ + ': ' + str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        if not delegated:
            connection.close()

def owner_worker(*args, root, source, release_contract=None):
    if __package__:
        from . import native_heart_worker as original
        from .lean_ps_guard import verify_source
        from .joint_startup import replace_attribute
    else:
        import native_heart_worker as original
        from lean_ps_guard import verify_source
        from joint_startup import replace_attribute
    verify_source(root, source, hardware=True) if release_contract is None else public_prepared(root, release_contract, hardware=True)
    with replace_attribute(original, 'ps_worker', partial(ps_worker, root=root, source=source, release_contract=release_contract)):
        return original.worker(*args, release_contract=release_contract)

def start_owner(context, *args, root, source, release_contract=None):
    child = context.Process(target=partial(owner_worker, root=root, source=source, release_contract=release_contract), args=args, name='joint25-lean-native-ps-owner', daemon=False)
    child.start()
    return child
