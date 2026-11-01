"""Pure new-package checks before the preserved verification/import paths."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

BASE='4c1ea19fbe72e2f9a8334d4d8615cf86b1d651aee6053c778275294e804ce594'
REPLAY='65c1f1ceef1720297584558249f85444d2a543afec1dee3bfd01e92de2ab98fe'
NAME='scalar-live-manifest.json'
BOOK='ScalarLive60.ipynb'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def book_identity(path):
    b=json.loads(Path(path).read_bytes());k=b['metadata']['kernelspec']
    return hashlib.sha256(json.dumps([b['nbformat'],k['name'],k['language'],
        [(c['cell_type'],''.join(c['source'])) for c in b['cells']]],
        ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def verify(root,expected):
    root=Path(root).resolve()
    if sha(root/NAME)!=expected:raise ValueError('scheduled live manifest differs')
    d=json.loads((root/NAME).read_bytes())
    if (d.get('schema')!='scalar_live60_v1' or d.get('baseline_sha256')!=BASE
        or d.get('qualified_replay_manifest_sha256')!=REPLAY
        or d.get('live60_passed') is not False):raise ValueError('scheduled live scope differs')
    for name,digest in d['added_files'].items():
        part=PurePosixPath(name);p=root/name
        if part.is_absolute() or '..' in part.parts or ':' in name or '\\' in name or p.is_symlink() or not p.resolve(strict=True).is_relative_to(root):
            raise ValueError('unsafe scheduled live member')
        if (book_identity(p) if name==BOOK else sha(p))!=digest:raise ValueError('scheduled live member differs: '+name)
        if name.endswith('.py') and '/' not in name:
            mod=sys.modules.get(name[:-3])
            if mod is not None and Path(mod.__file__).resolve()!=p:raise ValueError('mixed scheduled live module: '+name)
    if json.loads((root/BOOK).read_bytes())['metadata']['scalar_manifest_sha256']!=expected:
        raise ValueError('scheduled notebook handoff differs')
    from scheduled_live_guard import verify as retained
    result=retained(root,'9c43e9f08f9c215953ffd099b09da30c773b6d738463fb0a2d4f50b12dcc433e')
    policy=json.loads((root/'lean-joint-manifest.json').read_bytes())['policy']
    if d['policy']!=policy:raise ValueError('original policy changed')
    return dict(result,scalar_manifest_sha256=expected,scalar_live60_passed=False,
        hardware_accessed=False,heart_capture_started=False,original_display_period_ms=500)
