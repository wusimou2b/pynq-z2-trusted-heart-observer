"""Stdlib-only identity and post-run checks for the heart-only snapshot candidate."""
import json
from pathlib import Path

if __package__:
    from .joint_heart_guard import FLAGS, sha, write_new, notebook_code_hash, verify_package
else:
    from joint_heart_guard import FLAGS, sha, write_new, notebook_code_hash, verify_package

BASE_MANIFEST_SHA = '3f2170941f20de3104f71bbdfed5c0eaa258d9a6dffaf203576877dc71929d97'
ADDONS = {'heart_snapshot_guard.py', 'heart_snapshot_worker.py', 'run_heart_snapshot.py',
          'README_HEART_SNAPSHOT.md', 'joint_snapshot.py', 'joint_boundary.py'}
MANIFEST = 'heart-snapshot-manifest.json'
NOTEBOOK = 'HeartSnapshot25.ipynb'


def verify_candidate(root):
    root = Path(root).resolve()
    if sha(root/'joint-heart-manifest.json') != BASE_MANIFEST_SHA:
        raise ValueError('original heart release identity changed')
    original = verify_package(root)
    doc = json.loads((root/MANIFEST).read_text(encoding='utf-8'))
    if (doc.get('schema') != 'v3b25_heart_snapshot_package_v1'
            or doc.get('base_manifest_sha256') != BASE_MANIFEST_SHA
            or set(doc.get('files', {})) != ADDONS
            or (doc.get('raw_hz'), doc.get('processing_hz'), doc.get('duration_seconds')) != (25, 25, 60)
            or doc.get('heart_realtime_recovered') is not False
            or doc.get('video_enabled') is not False
            or doc.get('snapshot_probe_enabled') is not False
            or any(doc.get(key) is not False for key in FLAGS)):
        raise ValueError('heart snapshot candidate scope/identity mismatch')
    for name, digest in doc['files'].items():
        path = root/name
        if path.is_symlink() or not path.is_file() or sha(path) != digest:
            raise ValueError('candidate file identity mismatch: '+name)
    if notebook_code_hash(root/NOTEBOOK) != doc.get('notebook_code_sha256'):
        raise ValueError('candidate executable Notebook code changed')
    return dict(original, candidate_manifest_sha256=sha(root/MANIFEST),
                heart_realtime_recovered=False, video_enabled=False, snapshot_probe_enabled=False)


def assess(original, owner, *, inputs_unchanged, wrapper_error=None, post_errors=()):
    snapshot = owner.get('snapshot') or {}
    checks = dict(
        original_static_pilot=original.get('joint_heart_static_pilot_completed') is True,
        single_binding=owner.get('binding_instances') == 1 and owner.get('prepare_calls') == 1,
        snapshot_installed=snapshot.get('installed') is True,
        snapshot_restored=snapshot.get('restored') is True,
        one_construction=snapshot.get('final_snapshot_constructions') == 1,
        original_guard=snapshot.get('original_guard_retained') is True,
        no_cache=snapshot.get('status_cached') is False,
        no_probe=owner.get('snapshot_probe_started') is False,
        cleanup=owner.get('cleanup_confirmed') is True,
        no_errors=wrapper_error is None and not post_errors
            and owner.get('post_errors') == []
            and all(owner.get(key) is None for key in
                    ('wrapper_error', 'install_error', 'restore_error', 'prepare_error', 'release_error')),
        inputs_unchanged=bool(inputs_unchanged))
    return dict(schema='v3b25_heart_snapshot_trial_v1', checks=checks,
        heart_snapshot_static_pilot_completed=all(checks.values()),
        wrapper_error=wrapper_error, post_errors=list(post_errors),
        heart_realtime_recovered=False, strict_realtime_verified=False, accuracy_verified=False,
        camera_started=False, hdmi_started=False, video_on_joint_passed=False,
        concurrent60_passed=False, **FLAGS,
        scope_cn='仅快照等价减负的25Hz心率单测；基础完整不代表心率实时恢复，仍需核查积压/时效/真实显示。')
