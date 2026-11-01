"""Parent-only candidate identity; retained workers keep their original checks."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

BASE = 'c5210a87203f34a833bdf0a4b2080b92bf012908c3520d36a60dcd878acaae33'
NAME = 'handoff-live-manifest.json'
BOOK = 'HandoffLive60.ipynb'
REPLAY = '98a7d314ac3da53cce878f653bfd728cd517c46812b23bbc9e5feac72e197381'
POLICY = dict(raw_hz=25, processing_hz=25, video_fps=5, formal_seconds=60,
              display_age_ns=100_000_000, initial_lock_seconds=.05, maximum_reads=2,
              recheck_wait_seconds=0, source_age_seconds=1, protections_changed=False,
              automatic_retry=False, route_recovery_preserved=True)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def book_identity(path):
    b = json.loads(Path(path).read_bytes()); k = b['metadata']['kernelspec']
    return hashlib.sha256(json.dumps([b['nbformat'], k['name'], k['language'],
        [(c['cell_type'], ''.join(c['source'])) for c in b['cells']]],
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def verify(expected, root):
    root = Path(root).resolve(strict=True)
    if sha(root/NAME) != expected: raise ValueError('handoff live manifest differs')
    doc = json.loads((root/NAME).read_bytes())
    if (doc.get('schema'), doc.get('retained_manifest_sha256'), doc.get('qualified_replay_sha256'),
        doc.get('policy'), doc.get('live60_passed')) != (
            'handoff_live60_v1', BASE, REPLAY, POLICY, False):
        raise ValueError('handoff live policy differs')
    for name, digest in doc['added_files'].items():
        part, path = PurePosixPath(name), root/name
        if (part.is_absolute() or '..' in part.parts or ':' in name or '\\' in name
            or path.is_symlink() or not path.resolve(strict=True).is_relative_to(root)):
            raise ValueError('unsafe handoff live member')
        if (book_identity(path) if name == BOOK else sha(path)) != digest:
            raise ValueError('handoff live member differs: '+name)
        if name.endswith('.py'):
            mod = sys.modules.get(name[:-3])
            if mod is not None and Path(mod.__file__).resolve() != path:
                raise ValueError('mixed handoff live module: '+name)
    if json.loads((root/BOOK).read_bytes())['metadata']['handoff_manifest_sha256'] != expected:
        raise ValueError('handoff live Notebook pin differs')
    proof = json.loads((root/'qualified-handoff-replay.json').read_bytes())
    if not proof['software_checks_passed'] or proof['archive_sha256'] != REPLAY or proof['points'] != 1505:
        raise ValueError('saved replay prerequisite differs')
    from route_live_guard import verify as retained
    original = retained(root, BASE)
    return dict(original, handoff_manifest_sha256=expected, live60_passed=False,
                hardware_accessed=False, heart_capture_started=False)
