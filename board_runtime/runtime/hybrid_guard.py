"""Additive package identity over the complete-motion/browser baseline."""
import json
from pathlib import Path

if __package__:
    from .video_motion_guard import verify_package as verify_base
    from .spatial_camera_guard import sha,notebook_identity
    from .lean_ps_guard import local
else:
    from video_motion_guard import verify_package as verify_base
    from spatial_camera_guard import sha,notebook_identity
    from lean_ps_guard import local

MANIFEST='hybrid-display-manifest.json'
BOOK='HybridDisplay25.ipynb'
FILES={'hdmi_dashboard_model.py','hybrid_display.py','hybrid_worker.py','hybrid_guard.py',
    'hybrid_assessment.py','run_hybrid_display.py','README_HYBRID.md'}
BASE_MANIFEST_SHA='ea3a83f90a21bcb6d33564096bbce2c7d64ac7bfb075381c4997421725de3f83'


def verify_package(root,expected_manifest_sha=None):
    root=Path(root).resolve();base=verify_base(root)
    if base['manifest_sha256']!=BASE_MANIFEST_SHA:raise ValueError('complete-motion baseline changed')
    path=local(root,MANIFEST)
    if expected_manifest_sha is not None and sha(path)!=expected_manifest_sha:raise ValueError('hybrid identity changed')
    doc=json.loads(path.read_text('utf-8'))
    if (doc.get('schema')!='v3b25_hybrid_display_package_v1' or set(doc.get('files',{}))!=FILES
        or doc.get('base_manifest_sha256')!=BASE_MANIFEST_SHA
        or doc.get('layout')!='camera_bpm_strip_v1'
        or [doc.get(k) for k in ('raw_hz','processing_hz','video_fps','warmup_slots','startup_seconds','ready_seconds','join_seconds')]
            !=[25,25,5,700,180,60,1]
        or doc.get('duration_mode')!='manual_until_stop_v1' or doc.get('hdmi_curve_count')!=0
        or doc.get('browser_graphics_enabled') is not True
        or any(doc.get(k) is not False for k in ('algorithm_changed','gc_changed','protections_changed',
            'board_tested','accuracy_verified','full_v3b_acceptance_passed'))):raise ValueError('hybrid scope changed')
    for name,pin in doc['files'].items():
        if sha(local(root,name))!=pin:raise ValueError('hybrid source changed: '+name)
    if notebook_identity(local(root,BOOK))!=doc.get('notebook_identity_sha256'):raise ValueError('hybrid Notebook changed')
    return dict(base,base_manifest_sha256=BASE_MANIFEST_SHA,manifest_sha256=sha(path),
        browser_graphics_enabled=True,hdmi_curve_count=0,hdmi_layout=doc['layout'])
