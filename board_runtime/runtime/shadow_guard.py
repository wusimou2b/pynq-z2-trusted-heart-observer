"""Cold composite identity: unchanged heart, qualified spatial camera, new shadow."""
import json
from pathlib import Path
from zipfile import ZipFile

if __package__:
    from .continuous_guard import verify_package as verify_heart
    from .spatial_camera_guard import verify_package as verify_camera, notebook_identity, sha
    from .lean_ps_guard import local
    from .shadow_video_core import profile
else:
    from continuous_guard import verify_package as verify_heart
    from spatial_camera_guard import verify_package as verify_camera, notebook_identity, sha
    from lean_ps_guard import local
    from shadow_video_core import profile

MANIFEST='shadow-fusion-manifest.json'
BOOK='ShadowFusion25.ipynb'
SOURCES={'shadow_video_core.py','shadow_imu.py','shadow_fusion.py','shadow_joint.py','shadow_assessment.py',
         'shadow_guard.py','shadow_worker.py','run_shadow.py'}
FILES=SOURCES|{'README_SHADOW_FUSION.md','shadow-rule.json','camera-qualification.zip','camera-qualification-launch.json'}
BASE_ZIP_SHA='393e9ca5af43483b217bb22a0dea1720d7eec85ca0935351123a62a8e06d43b7'
CAMERA_MANIFEST_SHA='976e4ae03a64ab89f7c48e60ea07492816a9237d29757fde09aea9192e7596b6'
CAMERA_ZIP_SHA='bfc2e713385288a8d1a536d376e13c362bd2c263199be0bf7a021f4291ff2c55'
CAMERA_LAUNCH_SHA='7eeb68c9b9a31c5e71dc488da0af768425c48698ed9aeb500bf2a06d16a40b02'
RULE_SHA='5c178390d0ae63623dbc6c5ca9c59b68340912b6bc184bdada94d85ada32e8d7'


def verify_package(root, expected_manifest_sha=None):
    root=Path(root).resolve()
    verify_heart(root)
    verify_camera(root)
    if sha(local(root,'spatial-camera-manifest.json'))!=CAMERA_MANIFEST_SHA:
        raise ValueError('qualified camera manifest differs')
    path=local(root,MANIFEST)
    if expected_manifest_sha is not None and sha(path)!=expected_manifest_sha:
        raise ValueError('shadow manifest changed after parent verification')
    doc=json.loads(path.read_text('utf-8'))
    if (doc.get('schema')!='v3b25_shadow_fusion_package_v1' or set(doc.get('files',{}))!=FILES
        or len(doc.get('baseline_files',{}))!=340 or len(doc.get('camera_files',{}))!=29
        or doc.get('baseline_zip_sha256')!=BASE_ZIP_SHA or doc.get('rule_sha256')!=RULE_SHA
        or [doc.get(k) for k in ('raw_hz','processing_hz','video_target_fps','startup_seconds','ready_seconds','warmup_slots','join_seconds','pair_max_ns')]
            !=[25,25,5,180,60,700,1,250_000_000]
        or doc.get('duration_mode')!='manual_until_stop_v1' or doc.get('shadow_only') is not True
        or any(doc.get(k) is not False for k in ('heart_control_enabled','heart_algorithm_changed','gc_changed','protections_changed',
            'automatic_retry','board_tested','accuracy_verified','full_v3b_acceptance_passed','history_branch_merged'))):
        raise ValueError('shadow package scope changed')
    for names in (doc['baseline_files'],doc['camera_files'],doc['files']):
        for name,pin in names.items():
            p=local(root,name)
            if name.endswith('.ipynb'):
                if notebook_identity(p)!=doc['base_notebook_identities'].get(name):
                    raise ValueError('shadow copied Notebook changed: '+name)
            elif sha(p)!=pin:
                raise ValueError('shadow package member changed: '+name)
    if notebook_identity(local(root,BOOK))!=doc.get('notebook_identity_sha256'):
        raise ValueError('shadow Notebook executable/ordered content changed')
    if profile()['sha256']!=RULE_SHA or json.loads(local(root,'shadow-rule.json').read_text('utf-8'))!=profile():
        raise ValueError('shadow frozen rule differs')
    if sha(local(root,'camera-qualification.zip'))!=CAMERA_ZIP_SHA or sha(local(root,'camera-qualification-launch.json'))!=CAMERA_LAUNCH_SHA:
        raise ValueError('returned camera qualification differs')
    with ZipFile(root/'camera-qualification.zip') as z:
        if len(z.namelist())!=len(set(z.namelist())) or z.testzip() is not None:
            raise ValueError('camera qualification ZIP corrupt')
        report=json.loads(z.read('report.json'))
    launch=json.loads((root/'camera-qualification-launch.json').read_text('utf-8'))
    if not (report.get('session_complete') is True and report.get('fault') is None and report.get('inputs_unchanged') is True
        and report.get('counts')==dict(records_saved=300,captured=300,submitted=300,pl_completed=300)
        and report['cleanup'].get('cleanup_complete') is True and report['video'].get('thread_exited') is True
        and launch.get('worker_exited') is True and launch.get('exitcode')==0
        and launch.get('child_force_terminated') is False and launch.get('cleanup_unconfirmed') is False):
        raise ValueError('camera qualification incomplete')
    return dict(bundle_validated=True,hardware_accessed=False,original_heart_files_preserved=340,
        camera_qualified=True,rule_sha256=RULE_SHA,manifest_sha256=sha(path),raw_hz=25,processing_hz=25,video_target_fps=5,
        duration_mode='manual_until_stop_v1',heart_control_enabled=False,board_tested=False,
        accuracy_verified=False,full_v3b_acceptance_passed=False)
