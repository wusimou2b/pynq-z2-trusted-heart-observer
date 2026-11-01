"""Cold identity and applicable original joint gates, without native-IIC claims."""
import json
from pathlib import Path, PurePosixPath

if __package__:
    from .heart_snapshot_guard import verify_candidate as verify_heart
    from .joint_heart_guard import sha, write_new, notebook_code_hash
    from .run_yuyv_video import verify_package as verify_video
    from .yuyv_joint_guard import install_assessment
    from .joint_concurrent_guard import assess_concurrent, FLAGS
else:
    from heart_snapshot_guard import verify_candidate as verify_heart
    from joint_heart_guard import sha, write_new, notebook_code_hash
    from run_yuyv_video import verify_package as verify_video
    from yuyv_joint_guard import install_assessment
    from joint_concurrent_guard import assess_concurrent, FLAGS

MANIFEST = 'heart-video5-manifest.json'
NOTEBOOK = 'HeartVideo60.ipynb'
HEART_SHA = '6d4dc83a22e34285fc9ad3eec374b8abc82e07bdf3ea7fc8d1c4205ff3477834'
VIDEO_SHA = 'b91add10c68ebab68d6dfa0238bb65b4af0543acef8e8cb53337626dae36c9a8'
ADDONS = {'heart_video_binding.py', 'heart_video_worker.py', 'heart_video_guard.py',
          'run_heart_video.py', 'README_HEART_VIDEO.md'}
PAIR = {'heart_v3b25_yuyv.bit': '99a19202c167738b934cfb3247eae836425a68f510c3ec35fffd83c4b1a8b0a2',
        'heart_v3b25_yuyv.hwh': '6a57237e2ed1f21f07d8d09d7898aacd0424bc14cac16e8280274cc11478f313'}


def verify_package(root):
    root = Path(root).resolve()
    if sha(root/'heart-snapshot-manifest.json') != HEART_SHA or sha(root/'yuyv-video-manifest.json') != VIDEO_SHA:
        raise ValueError('reviewed heart/video release changed')
    heart = verify_heart(root)
    verify_video(root)
    path = root/MANIFEST
    if path.is_symlink(): raise ValueError('candidate manifest symlink')
    doc = json.loads(path.read_text('utf-8'))
    if (doc.get('schema') != 'v3b25_heart_video5_package_v1'
        or doc.get('heart_manifest_sha256') != HEART_SHA or doc.get('video_manifest_sha256') != VIDEO_SHA
        or not ADDONS <= set(doc.get('files', {})) or doc.get('pair_sha256') != PAIR
        or tuple(doc.get(k) for k in ('raw_hz', 'processing_hz', 'video_target_fps', 'formal_seconds',
            'warmup_slots', 'startup_timeout_seconds', 'ps_warmup_timeout_seconds')) != (25,25,5,60,700,180,60)
        or doc.get('iic_runtime') != 'original_pynq_sensorbus' or doc.get('snapshot_probe_started') is not False
        or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('heart/video package scope changed')
    for name, digest in doc['files'].items():
        rel = PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or '\\' in name or ':' in name:
            raise ValueError('invalid package member')
        p = root/name
        if p.is_symlink() or not p.is_file() or sha(p) != digest:
            raise ValueError('heart/video source identity changed: '+name)
    if (root/NOTEBOOK).is_symlink() or notebook_code_hash(root/NOTEBOOK) != doc.get('notebook_code_sha256'):
        raise ValueError('heart/video Notebook code changed')
    return dict(bundle_validated=True, hardware_accessed=False,
        frozen_files_verified=heart['frozen_files_verified'], package_manifest_sha256=sha(path),
        raw_hz=25, processing_hz=25, video_target_fps=5, formal_seconds=60,
        startup_timeout_seconds=180, iic_runtime='original_pynq_sensorbus', **FLAGS)


def assess_candidate(directory, inherited, owner, *, inputs_unchanged, wrapper_error=None):
    with install_assessment(PAIR):
        result = assess_concurrent(directory, inherited, owner,
            inputs_unchanged=inputs_unchanged, wrapper_error=wrapper_error)
    snap = owner.get('snapshot') or {}
    pre = (inherited.get('summary') or {}).get('preflight') or {}
    result['checks'].update(
        recovered_iic=owner.get('iic_runtime') == pre.get('iic_runtime') == 'original_pynq_sensorbus'
            and owner.get('native_iic_started') is False and pre.get('native_iic_started') is False,
        no_probe=owner.get('snapshot_probe_started') is False and pre.get('snapshot_probe_started') is False,
        recovered_snapshot=snap.get('installed') is True and snap.get('restored') is True
            and snap.get('final_snapshot_constructions') == 1 and snap.get('original_guard_retained') is True
            and snap.get('status_cached') is False and owner.get('snapshot_cleanup_confirmed') is True,
        no_adapter_errors=all(owner.get(k) is None for k in
            ('install_error','restore_error','prepare_error','release_error')))
    result.update(schema='v3b25_heart_video5_trial_v1',
        joint_60s_pilot_completed=all(result['checks'].values()),
        snapshot=snap, iic_runtime=owner.get('iic_runtime'),
        strict_realtime_verified=False, accuracy_verified=False,
        scope_cn='25/25Hz心率恢复版＋5fps PL视频共同60秒；原PYNQ IIC，无逐拍Probe。基础完整仍须人工核心率时效/动态画面；不是准确率、15fps、DDR或完整V3B验收。')
    return result
