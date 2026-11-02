"""Pure file identity before any board/native imports."""
import hashlib,json,sys
from pathlib import Path,PurePosixPath

BASE_SHA='a7a0f62e4f4a15e691553285dcff54abc4ad8fa96522fbd84a01720a975f7690'
MANIFEST='fault-replay-manifest.json'
POLICY=dict(points=1071,warmup=700,ready_seconds=60,startup_seconds=300,
    step_seconds=1,exit_seconds=1,rtl_seconds=.020,native_seconds=.040,
    fresh_capture=False,video=False,automatic_retry=False)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def verify(root,expected):
    root=Path(root).resolve();path=root/MANIFEST
    if sha(path)!=expected:raise ValueError('replay manifest identity differs')
    d=json.loads(path.read_bytes())
    if d.get('schema')!='compact_fault_saved1071_v1' or d.get('policy')!=POLICY or d.get('baseline_sha256')!=BASE_SHA:
        raise ValueError('replay policy/baseline differs')
    for name,pin in d['files'].items():
        p=PurePosixPath(name);f=root/name
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name or f.is_symlink() or not f.resolve(strict=True).is_relative_to(root):
            raise ValueError('replay path escaped')
        if sha(f)!=pin:raise ValueError('replay file differs: '+name)
    return d

def baseline(root):
    root=Path(root).resolve()
    if sha(root/'compact-delivery-manifest.json')!=BASE_SHA:raise ValueError('retained baseline changed')
    if str(root) not in sys.path:sys.path.insert(1,str(root))
    import compact_delivery_guard
    if Path(compact_delivery_guard.__file__).resolve()!=root/'compact_delivery_guard.py':raise ValueError('mixed baseline imports')
    return compact_delivery_guard.verify(root,BASE_SHA)
