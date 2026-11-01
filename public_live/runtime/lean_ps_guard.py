"""Cold immutable candidate identity; source ARM module stays at its real root."""
import json
from pathlib import Path
import sys

if __package__:
    from .native_heart_guard import verify_package as verify_native, sha, write_new, notebook_code_hash
    from .native_heart_prepare import validate_prepared
else:
    from native_heart_guard import verify_package as verify_native, sha, write_new, notebook_code_hash
    from native_heart_prepare import validate_prepared

SOURCE_SHA = '7a492ec62bac4b349c5df1c4fef4f3c38a51f981dc31008afc2d03d50e8bc836'
PREPARED_SHA = 'e174377658d39245e3b40b7ceed36e51ce30ed0892b26f0332ff9abea05e100d'
BINARY_SHA = '4dc17698315564f4d2ac50b5e3d1607fecfe12f2520dafa9f4aaa40ff4e50c78'
FILES = {'lean_ps_worker.py', 'lean_ps_guard.py', 'run_lean_ps.py',
         'README_LEAN_PS.md', 'native-prepare-results.zip'}
BOOK = 'LeanPS60.ipynb'
MANIFEST = 'lean-ps-manifest.json'


def local(root, name):
    p = Path(name)
    if not name or p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('invalid lean PS package path')
    target = root/p
    if target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):
        raise ValueError('lean PS package path escaped')
    return target


def verify_package(root):
    root = Path(root).resolve()
    for name in ('run_lean_ps', 'lean_ps_worker', 'run_native_heart', 'native_heart_worker',
                 'run_browser_heart', 'run_heart_video', 'run_joint_concurrent5'):
        m = sys.modules.get(name)
        if m is not None and Path(m.__file__).resolve() != root/(name+'.py'):
            raise RuntimeError('mixed lean PS runtime root: '+name)
    native = verify_native(root)
    d = json.loads(local(root, MANIFEST).read_text('utf-8'))
    if (d.get('schema') != 'v3b25_lean_ps_package_v1' or set(d.get('files', {})) != FILES
        or len(d.get('base_files', {})) != 312 or d.get('source_manifest_sha256') != SOURCE_SHA
        or [d.get(k) for k in ('raw_hz', 'processing_hz', 'video_fps', 'warmup_slots', 'formal_seconds', 'join_seconds')]
           != [25, 25, 5, 700, 60, 1]
        or any(d.get(k) is not False for k in ('algorithm_changed', 'limits_changed', 'gc_changed', 'history_candidate_merged'))):
        raise ValueError('lean PS package scope differs')
    for n, h in {**d['base_files'], **d['files']}.items():
        path = local(root, n)
        if n.endswith('.ipynb'):
            if notebook_code_hash(path) != d['base_notebook_code'][n]:
                raise ValueError('lean PS base Notebook code changed')
        elif sha(path) != h:
            raise ValueError('lean PS package file changed: '+n)
    if notebook_code_hash(local(root, BOOK)) != d['notebook_code_sha256']:
        raise ValueError('lean PS Notebook code changed')
    return dict(native, lean_manifest_sha256=sha(root/MANIFEST))


def verify_source(root, source, *, hardware=False, host_check=False):
    root, source = Path(root).resolve(), Path(source).resolve()
    if host_check and hardware:
        raise ValueError('host check cannot authorize hardware')
    verify_package(root)
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError('lean PS source must be a separate original root')
    if sha(source/'native-heart-manifest.json') != SOURCE_SHA:
        raise ValueError('original Native100 manifest changed')
    prepared = validate_prepared(source, hardware=hardware)
    if not host_check and (prepared['host_check'] or not prepared['arm_native']
        or prepared['preparation_sha256'] != PREPARED_SHA or prepared['binary']['sha256'] != BINARY_SHA):
        raise ValueError('original ARM preparation/binary differs')
    return dict(prepared, source_root=str(source), runtime_root=str(root))
