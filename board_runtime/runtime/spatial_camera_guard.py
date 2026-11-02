"""Builtin-only package and successful static-qualification checks."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

BOOK='SpatialCamera60.ipynb'
MANIFEST='spatial-camera-manifest.json'
PAIR_HASHES={'heart_v3b25_spatial.bit':'688828371d72c9e1a8ad611d4b980c2583e482e2906f834eb943bdfd408e6e10',
    'heart_v3b25_spatial.hwh':'aef5e1f21d7b18d952cf8d73a58180e4d46c20e074307f7ccf56e7275dfb304b'}
STATIC_RESULT_SHA='e4f8273ce2bdd90444c22a2bf98a10a8221a165061ae1558420969925d36ea08'
STATIC_LAUNCH_SHA='00e230045e8ec6c9f69ec5bcc323f3e094757bba274f9cbbf68d34251cbd8155'
SOURCE_FILES={'run_spatial_camera.py','spatial_camera_guard.py','spatial_camera.py','spatial_features.py','README_SPATIAL_CAMERA.md',
    'spatial_owner.py','spatial_transport.py','spatial_mailbox.py','joint_owner.py','yuyv_owner.py','yuyv_transport.py',
    'yuyv_reference.py','yuyv_runtime.py','joint_video_transport.py','joint_video_runtime.py','joint_video_guard.py',
    'joint_video_five.py','joint_video_live_guard.py','run_roi_motion.py','roi_motion_core.py','vision_reference.py','spatial_reference.py'}
EVIDENCE_FILES={'static-qualification.zip','static-qualification-launch.json'}
FILES=SOURCE_FILES|set(PAIR_HASHES)|{'spatial-artifacts.json'}|EVIDENCE_FILES
FALSE_FLAGS=('automatic_retry','classification_performed','thresholds_refitted','heart_capture_started','imu_capture_started',
    'heart_ps_started','camera_board_tested','board_ddr_verified','three_class_acceptance_passed','accuracy_verified','full_v3b_acceptance_passed')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def notebook_identity(path):
    nb=json.loads(Path(path).read_text('utf-8'));kernel=nb['metadata']['kernelspec']
    identity=[nb['nbformat'],kernel['name'],kernel['language'],[(c['cell_type'],''.join(c['source'])) for c in nb['cells']]]
    return hashlib.sha256(json.dumps(identity,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def verify_static(root):
    root=Path(root)
    if sha(root/'static-qualification.zip')!=STATIC_RESULT_SHA or sha(root/'static-qualification-launch.json')!=STATIC_LAUNCH_SHA:
        raise ValueError('successful static qualification changed')
    with ZipFile(root/'static-qualification.zip') as z:
        if len(z.namelist())!=len(set(z.namelist())) or z.testzip() is not None:raise ValueError('static proof ZIP corrupt')
        report=json.loads(z.read('report.json'));artifacts=json.loads(z.read('spatial-artifacts.json'))
        if artifacts.get('files')!=PAIR_HASHES:raise ValueError('camera pair not the static-tested pair')
        if not (report.get('session_complete') is True and report.get('fault') is None and report.get('cases_checked')==8
            and report.get('valid_pair_cases')==6 and report.get('inputs_unchanged') is True
            and all(c.get('matched') is True for c in report['cases'])
            and all(report['cleanup'].get(k) is True for k in ('cleanup_complete','buffers_released','actual_lease_released'))):
            raise ValueError('static proof did not pass')
    launch=json.loads((root/'static-qualification-launch.json').read_text('utf-8'))
    if not launch.get('worker_exited') or launch.get('exitcode')!=0 or launch.get('child_force_terminated') is not False:
        raise ValueError('static test did not naturally exit')
    return dict(result_sha256=STATIC_RESULT_SHA,launch_sha256=STATIC_LAUNCH_SHA,cases=8,valid_pairs=6)


def verify_package(root):
    root=Path(root).resolve();path=root/MANIFEST
    if path.is_symlink():raise ValueError('package manifest symlink')
    d=json.loads(path.read_text('utf-8'))
    if (d.get('schema')!='v3b25_spatial_camera_package_v1' or set(d.get('files',{}))!=FILES
        or (d.get('formal_seconds'),d.get('target_fps'),d.get('startup_seconds'),d.get('transfer_seconds'),d.get('pair_max_ns'),d.get('pixel_threshold'))!=(60,5,180,1,250000000,8)
        or d.get('phases')!=['STATIC','LIGHT','HEAVY','STATIC'] or d.get('transition_seconds')!=2
        or any(d.get(k) is not False for k in FALSE_FLAGS)):
        raise ValueError('spatial camera package scope changed')
    for name,digest in d['files'].items():
        p=root/name
        if p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root) or sha(p)!=digest:
            raise ValueError('spatial camera member changed: '+name)
    if (root/BOOK).is_symlink() or notebook_identity(root/BOOK)!=d.get('notebook_identity_sha256'):
        raise ValueError('spatial camera Notebook semantics changed')
    pair=json.loads((root/'spatial-artifacts.json').read_text('utf-8'))
    if pair.get('files')!=PAIR_HASHES or (pair.get('magic'),pair.get('version'))!=(0x56334232,0x20000):
        raise ValueError('spatial camera pair declaration changed')
    if any(d['files'][name]!=pin for name,pin in PAIR_HASHES.items()):raise ValueError('static-qualified pair bytes differ')
    qualified=verify_static(root)
    return dict(bundle_validated=True,hardware_accessed=False,files_verified=len(FILES),manifest_sha256=sha(path),
        spatial_static_qualified=True,static_qualification=qualified,formal_seconds=60,target_fps=5,pixel_threshold=8,
        grid=[4,3],heart_capture_started=False,heart_ps_started=False,imu_capture_started=False,camera_started=False,hdmi_started=False,
        camera_board_tested=False,classification_performed=False,three_class_acceptance_passed=False,board_ddr_verified=False)
