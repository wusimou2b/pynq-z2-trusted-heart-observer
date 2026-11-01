"""Original PS target with its unused offline Pandas dependency deferred.

No frozen source, function code, arithmetic, GC or process-exit policy changes.
Only three verified modules' own import dictionaries receive a lazy Pandas
reference. Real attribute use imports the installed library, not a substitute.
"""
import builtins
from contextlib import contextmanager
import hashlib
import importlib
from importlib.machinery import PathFinder
from pathlib import Path
import sys

SOURCES = {
    'heart_v2.dataset': (
        'frozen/base/deps/static/checked/base/heart_v2/dataset.py',
        'f8a2ca2e41b264095f6760f15985b55e374425a2b0a52c7b50f7f7a5cd02ecf2'),
    'heart_v2.runtime_main_chain': (
        'frozen/base/deps/static/checked/base/heart_v2/runtime_main_chain.py',
        'bba4d659c05d84a4ca177d18b7c44bd5a1c52b68ae08e771d86fde190e9c06dc'),
    'heart_v3a.runtime_pl_chain': (
        'frozen/base/deps/static/checked/base/heart_v3a/runtime_pl_chain.py',
        '902cd4ef772c1243c7ec82bfcbdd30672267daa192096ecac307e83038470af5'),
}


class DeferredPandas:
    def __init__(self):
        self._module = None

    def __getattr__(self, name):
        if self._module is None:
            self._module = importlib.import_module('pandas')
        return getattr(self._module, name)


@contextmanager
def defer_offline_pandas(root):
    """Apply only in a fresh, owned PS child; retain real imports everywhere else."""
    root = Path(root).resolve()
    if 'pandas' in sys.modules or any(name in sys.modules for name in SOURCES):
        raise RuntimeError('deferred offline imports require a fresh PS; dependency preloaded')
    paths = {}
    for name, (relative, pin) in SOURCES.items():
        path = root / relative
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != pin:
            raise ValueError('deferred import source identity differs: ' + name)
        paths[name] = path.resolve(strict=True)
    normal_import = builtins.__import__
    pandas = DeferredPandas()

    def local_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'pandas' and not fromlist and level == 0:
            return pandas
        return normal_import(name, globals, locals, fromlist, level)

    class Loader:
        def create_module(self, spec):
            return None

        def exec_module(self, module):
            path = paths[module.__name__]
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != SOURCES[module.__name__][1]:
                raise ValueError('deferred import source changed before execution')
            # Do not trust/rewrite a cached pyc, or alter the interpreter's
            # builtins. Every original function body is compiled unmodified.
            module.__dict__['__builtins__'] = dict(vars(builtins), __import__=local_import)
            exec(compile(data, str(path), 'exec', dont_inherit=True), module.__dict__)

    class Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname not in paths:
                return None
            spec = PathFinder.find_spec(fullname, path)
            if spec is None or spec.origin is None or Path(spec.origin).resolve() != paths[fullname]:
                raise RuntimeError('deferred import resolved to a different frozen module')
            spec.loader = Loader()
            return spec

    finder = Finder()
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        sys.meta_path.remove(finder)


def ps_worker(connection, source, *, root, **kwargs):
    delegated = False
    try:
        if __package__:
            from .main_heart_process import ps_worker as original
        else:
            from main_heart_process import ps_worker as original
        with defer_offline_pandas(root):
            delegated = True
            return original(connection, source, root=root, **kwargs)
    except BaseException as exc:
        if delegated:
            raise
        try:
            connection.send((0, 'error', type(exc).__name__ + ': ' + str(exc)))
        except (OSError, EOFError):
            pass
    finally:
        if not delegated:
            connection.close()
