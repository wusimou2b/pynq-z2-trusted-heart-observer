"""Pure new-package checks before the preserved verification/import paths."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

BASE='62932cb0cea6b819d8a0083a2efc0bafded26fb5409b21832da30654cc2a1de5'
REPLAY='0cf546c6dddae317c621cec379a34914375e4e4fae21ae77af9b6a1f1c3c3836'
NAME='route-live-manifest.json'
BOOK='RouteRecovery60.ipynb'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def book_identity(path):
    b=json.loads(Path(path).read_bytes());k=b['metadata']['kernelspec']
    return hashlib.sha256(json.dumps([b['nbformat'],k['name'],k['language'],
        [(c['cell_type'],''.join(c['source'])) for c in b['cells']]],
        ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def verify_new(root,expected):
    root=Path(root).resolve()
    if sha(root/NAME)!=expected:raise ValueError('scheduled live manifest differs')
    d=json.loads((root/NAME).read_bytes())
    if (d.get('schema')!='route_live60_v1' or d.get('baseline_sha256')!=BASE
        or d.get('qualified_replay_manifest_sha256')!=REPLAY
        or d.get('live60_passed') is not False
        or d.get('qualified_route_replay_sha256') != 'b9bde74ffbbf37a3108e2405488e41c4fec343148104b095df4b8c64e183feb7'):raise ValueError('scheduled live scope differs')
    for name,digest in d['added_files'].items():
        part=PurePosixPath(name);p=root/name
        if part.is_absolute() or '..' in part.parts or ':' in name or '\\' in name or p.is_symlink() or not p.resolve(strict=True).is_relative_to(root):
            raise ValueError('unsafe scheduled live member')
        if (book_identity(p) if name==BOOK else sha(p))!=digest:raise ValueError('scheduled live member differs: '+name)
        if name.endswith('.py') and '/' not in name:
            mod=sys.modules.get(name[:-3])
            if mod is not None and Path(mod.__file__).resolve()!=p:raise ValueError('mixed scheduled live module: '+name)
    if json.loads((root/BOOK).read_bytes())['metadata']['route_manifest_sha256']!=expected:
        raise ValueError('scheduled notebook handoff differs')
    return d


def verify(root,expected):
    root=Path(root).resolve()
    d=verify_new(root,expected)
    from state_wire_live_guard import verify as retained
    result=retained(root,'f76bcbde8997a50db2845b41349be8ec6c06cadfb82203b7f9c3861da45a4cb3')
    policy=json.loads((root/'lean-joint-manifest.json').read_bytes())['policy']
    if d['policy']!=policy:raise ValueError('original policy changed')
    return dict(result,route_manifest_sha256=expected,route_live60_passed=False,
        hardware_accessed=False,heart_capture_started=False,original_display_period_ms=500)
