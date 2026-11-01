"""Identity for the additive, manually started live60 candidate."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

NAME='lean-joint-manifest.json'
BOOK='LeanJoint60.ipynb'
BASE='d9d426e2451334adad75458bd6bbf38010995b3ba9fdca6ca8796f6e6dc067ee'
REPLAY='6b8e2a3dc122194f2ea152188c019a4a336eb8a7b10249d6569d369e03dbd9fe'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def book_identity(path):
    b=json.loads(Path(path).read_bytes());k=b['metadata']['kernelspec']
    return hashlib.sha256(json.dumps([b['nbformat'],k['name'],k['language'],
        [(c['cell_type'],''.join(c['source'])) for c in b['cells']]],
        ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def verify(root,expected):
    root=Path(root).resolve()
    if sha(root/NAME)!=expected:raise ValueError('lean joint manifest differs')
    d=json.loads((root/NAME).read_bytes())
    if d.get('schema')!='lean_joint60_v1' or d.get('baseline_sha256')!=BASE or d.get('replay_sha256')!=REPLAY:
        raise ValueError('lean joint scope differs')
    for name,digest in d['added_files'].items():
        part=PurePosixPath(name);p=root/name
        if part.is_absolute() or '..' in part.parts or ':' in name or '\\' in name or p.is_symlink() or not p.resolve(strict=True).is_relative_to(root):
            raise ValueError('unsafe lean member')
        if (book_identity(p) if name==BOOK else sha(p))!=digest:raise ValueError('lean member differs: '+name)
        if name.endswith('.py') and '/' not in name:
            mod=sys.modules.get(name[:-3])
            if mod is not None and Path(mod.__file__).resolve()!=p:raise ValueError('mixed lean module root: '+name)
    if json.loads((root/BOOK).read_bytes())['metadata']['lean_manifest_sha256']!=expected:
        raise ValueError('lean notebook handoff differs')
    # Additional identity is checked before importing any retained board path.
    from compact_delivery_guard import verify as baseline, POLICY
    if d['policy']!=POLICY:raise ValueError('original protection policy differs')
    checked=baseline(root,BASE)
    return dict(checked,lean_manifest_sha256=expected,live60_passed=False,
        saved1071_joint_replay_passed=True,ps_exit_margin_ms_observed=4.396493)
