"""Cold identity for the complete baseline-based motion entry."""
import json
from pathlib import Path

if __package__:
    from .shadow_guard import verify_package as verify_components
    from .spatial_camera_guard import sha, notebook_identity
    from .lean_ps_guard import local
else:
    from shadow_guard import verify_package as verify_components
    from spatial_camera_guard import sha, notebook_identity
    from lean_ps_guard import local

MANIFEST = 'full-motion-manifest.json'
BOOK = 'FullMotion25.ipynb'
SOURCES = {'video_motion_joint.py', 'video_motion_worker.py', 'video_motion_guard.py', 'run_video_motion.py'}
FILES = SOURCES | {'README_FULL_MOTION.md'}


def verify_package(root, expected_manifest_sha=None):
    root = Path(root).resolve()
    original = verify_components(root)
    path = local(root, MANIFEST)
    if expected_manifest_sha is not None and sha(path) != expected_manifest_sha:
        raise ValueError('complete motion manifest changed after preparation')
    doc = json.loads(path.read_text('utf-8'))
    if (doc.get('schema') != 'v3b25_baseline_full_motion_package_v1'
        or set(doc.get('files', {})) != FILES
        or doc.get('component_manifest_sha256') != original['manifest_sha256']
        or [doc.get(k) for k in ('raw_hz','processing_hz','video_fps','warmup_slots','startup_seconds','ready_seconds','join_seconds','preparation_hdmi_submissions')]
            != [25,25,5,700,180,60,1,4]
        or doc.get('duration_mode') != 'manual_until_stop_v1'
        or any(doc.get(k) is not True for k in ('video_and_mpu_fusion_enabled','original_start_order_retained'))
        or any(doc.get(k) is not False for k in ('heart_control_enabled','heart_algorithm_changed','gc_changed','protections_changed',
            'per_register_timing_enabled','ps_first_enabled','board_tested','accuracy_verified','full_v3b_acceptance_passed'))):
        raise ValueError('complete motion scope changed')
    for name,pin in doc['files'].items():
        if sha(local(root,name)) != pin:
            raise ValueError('complete motion source changed: '+name)
    if notebook_identity(local(root,BOOK)) != doc.get('notebook_identity_sha256'):
        raise ValueError('complete motion Notebook changed')
    return dict(original, component_manifest_sha256=original['manifest_sha256'], manifest_sha256=sha(path),
        video_and_mpu_fusion_enabled=True, original_start_order_retained=True, preparation_hdmi_submissions=4,
        per_register_timing_enabled=False, ps_first_enabled=False)
