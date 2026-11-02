"""Preserve successful332; validate only added identities in the physical owner."""
import json
from pathlib import Path

if __package__:
    from .lean_ps_guard import local, sha, notebook_code_hash
else:
    from lean_ps_guard import local, sha, notebook_code_hash

MANIFEST = 'continuous-manifest.json'
FILES = {'continuous_control.py','continuous_runtime.py','continuous_run.py',
         'continuous_guard.py','continuous_client.js','README_CONTINUOUS.md'}
BASE_ZIP_SHA = 'e8019f7f965700133de3e30892b8a7d6d39987b39ce50cff2d715b9ae09015b5'


def verify_additions(root, expected_manifest_sha=None):
    root = Path(root).resolve()
    path = local(root, MANIFEST)
    if expected_manifest_sha is not None and sha(path) != expected_manifest_sha:
        raise ValueError('continuous manifest changed after parent verification')
    d = json.loads(path.read_text('utf-8'))
    if (d.get('schema') != 'v3b25_continuous_package_v1' or set(d.get('files',{})) != FILES
        or d.get('original_zip_sha256') != BASE_ZIP_SHA or len(d.get('base_files',{})) != 332
        or [d.get(k) for k in ('raw_hz','processing_hz','video_fps','startup_seconds','ready_seconds','warmup_slots','join_seconds')]
            != [25,25,5,180,60,700,1] or d.get('duration_mode') != 'manual_until_stop_v1'
        or any(d.get(k) is not False for k in ('algorithm_changed','gc_changed','protections_changed','automatic_retry','board_tested'))):
        raise ValueError('continuous package scope changed')
    for n,h in d['files'].items():
        if sha(local(root,n)) != h:
            raise ValueError('continuous source changed: '+n)
    if notebook_code_hash(local(root,'Continuous25.ipynb')) != d.get('notebook_code_sha256'):
        raise ValueError('continuous Notebook executable changed')
    return d


def verify_package(root):
    root = Path(root).resolve()
    d = verify_additions(root)
    if __package__:
        from .joint_exit_guard import verify_package as original
    else:
        from joint_exit_guard import verify_package as original
    checked = original(root)
    for n,h in d['base_files'].items():
        p = local(root,n)
        actual = notebook_code_hash(p) if n.endswith('.ipynb') else sha(p)
        if actual != (d['base_notebook_code'][n] if n.endswith('.ipynb') else h):
            raise ValueError('successful baseline changed: '+n)
    return dict(checked, continuous_manifest_sha256=sha(root/MANIFEST),
        original_files_preserved=332, duration_mode='manual_until_stop_v1', board_tested=False)
