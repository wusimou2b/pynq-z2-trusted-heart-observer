"""Pure-file identity for a manual-duration wrapper around the frozen live60."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

BASE = '9552a9ce90f59dcecfff42c885f1fac5eb2e981cbc480c0ea7663f132dc4007b'
NAME = 'demo-continuous-manifest.json'
BOOK = 'ContinuousDemo25.ipynb'
POLICY = dict(raw_hz=25, processing_hz=25, video_fps=5,
    formal_seconds=None, duration_mode='manual_until_stop_v1',
    automatic_retry=False, epoch_validation=True, trace_capacity=65536,
    scheduling_record_capacity=8192, scheduling_extra_preallocated_bytes=393216,
    trace_overflow_stops=True, other_protections_changed=False,
    retained_files=632, hardware_algorithm_changed=False)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def book_identity(path):
    b = json.loads(Path(path).read_bytes()); k = b['metadata']['kernelspec']
    return hashlib.sha256(json.dumps([b['nbformat'], k['name'], k['language'],
        [(c['cell_type'], ''.join(c['source'])) for c in b['cells']]],
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def verify(expected, root):
    root = Path(root).resolve(strict=True)
    if sha(root/NAME) != expected: raise ValueError('continuous demo manifest differs')
    doc = json.loads((root/NAME).read_bytes())
    if (doc.get('schema'), doc.get('retained_manifest_sha256'), doc.get('policy')) != (
        'continuous_demo25_v1', BASE, POLICY):
        raise ValueError('continuous demo policy differs')
    for name, digest in doc['added_files'].items():
        part, path = PurePosixPath(name), root/name
        if (part.is_absolute() or '..' in part.parts or ':' in name or '\\' in name
            or path.is_symlink() or not path.resolve(strict=True).is_relative_to(root)):
            raise ValueError('unsafe continuous demo member')
        if (book_identity(path) if name == BOOK else sha(path)) != digest:
            raise ValueError('continuous demo member differs: '+name)
        if name.endswith('.py'):
            module = sys.modules.get(name[:-3])
            if module is not None and Path(module.__file__).resolve() != path:
                raise ValueError('mixed continuous demo module: '+name)
    if json.loads((root/BOOK).read_bytes())['metadata']['demo_manifest_sha256'] != expected:
        raise ValueError('continuous demo Notebook pin differs')
    # This import is pure validation, and is intentionally after new identity.
    from handoff_live_guard import verify as retained
    checked = retained(BASE, root)
    return dict(checked, demo_manifest_sha256=expected, formal_seconds=None,
        duration_mode=POLICY['duration_mode'], other_protections_changed=False,
        hardware_accessed=False, continuous_live_passed=False)
