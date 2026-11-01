"""Cold identities for the unchanged browser base and its native PS addon."""
import json
from pathlib import Path
from zipfile import ZipFile

if __package__:
    from .browser_heart_guard import verify_package as verify_browser
    from .joint_heart_guard import sha,write_new,notebook_code_hash
else:
    from browser_heart_guard import verify_package as verify_browser
    from joint_heart_guard import sha,write_new,notebook_code_hash

MANIFEST='native-heart-manifest.json'
NOTEBOOK='NativeHeartVideo60.ipynb'
BASE_SHA='ce541ef001f327234c3a30b4275d14458c2b3ed670edb77a27f23d7e6be8893d'
RECORD_SHA='e49c3ac12ed0822be9987ad01eb2004a9811ae03608efdb94c3e1eb82238f1bb'
ARM_SHA='82b49d16e05b17cc45a921b9850430def6c5ab4f473c81d25b1ddf3f09146041'
ARM_MANIFEST_SHA='2f220c2ba33ef93a2ee4ff4518043d8eabe7dabd4e5346981c90ab310d3f6e5f'
DEPENDENCIES={'statistics25_native.c','statistics25_native.py','statistics25_native_build.py',
    'statistics25_native_trial.py','statistics25_replay.py','statistics25_core.py',
    'statistics25_guard.py','ps_budget_runtime.py','ps_budget_guard.py'}
ADDONS=DEPENDENCIES|{'native_heart_guard.py','native_heart_prepare.py','native_heart_worker.py',
    'run_native_heart.py','README_NATIVE_HEART.md','native-arm-evidence.zip',
    'native-arm-manifest.json','native-input.zip','browser-budget.json'}


def local(root,name):
    p=Path(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:
        raise ValueError('invalid native package path')
    root=Path(root).resolve();path=root/p
    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
        raise ValueError('native package symlink/escape')
    return path


def verify_package(root):
    root=Path(root).resolve();base=verify_browser(root)
    doc=json.loads(local(root,MANIFEST).read_text('utf-8'))
    if (doc.get('schema')!='v3b25_native_heart_package_v1' or set(doc.get('files',{}))!=ADDONS
            or doc.get('browser_manifest_sha256')!=BASE_SHA or sha(root/'browser-heart-manifest.json')!=BASE_SHA
            or tuple(doc.get(k) for k in ('raw_hz','processing_hz','video_fps','formal_seconds','warmup_slots'))!=(25,25,5,60,700)
            or any(doc.get(k) is not False for k in ('algorithm_changed','runtime_limits_changed','board_tested'))):
        raise ValueError('native heart package scope changed')
    for n,h in doc['files'].items():
        if sha(local(root,n))!=h:raise ValueError('native heart file changed: '+n)
    if len(doc.get('base_files',{}))+len(doc.get('base_notebooks',{}))!=292:
        raise ValueError('native browser base file scope differs')
    for n,h in doc['base_files'].items():
        if sha(local(root,n))!=h:raise ValueError('native browser base changed: '+n)
    for n,h in doc['base_notebooks'].items():
        if notebook_code_hash(local(root,n))!=h:raise ValueError('native browser Notebook changed: '+n)
    if notebook_code_hash(local(root,NOTEBOOK))!=doc.get('notebook_code_sha256'):
        raise ValueError('native heart Notebook code changed')
    if (sha(root/'native-input.zip')!=RECORD_SHA or sha(root/'native-arm-evidence.zip')!=ARM_SHA
            or sha(root/'native-arm-manifest.json')!=ARM_MANIFEST_SHA):
        raise ValueError('reviewed native/input evidence changed')
    qualified=json.loads((root/'native-arm-manifest.json').read_text('utf-8'))
    for n in DEPENDENCIES|{'joint_startup.py'}:
        if sha(root/n)!=qualified['files'][n]:raise ValueError('qualified native dependency changed: '+n)
    with ZipFile(root/'native-arm-evidence.zip') as z:
        if z.testzip() is not None:raise ValueError('ARM evidence ZIP corrupt')
        arm=json.loads(z.read('native100.json'))
    if not (arm['arm_native'] and arm['diagnostic_complete'] and arm['candidate_budget_passed']
            and arm['error'] is None and arm['trial']['proof']['passed']
            and arm['trial']['timing']['gate']['passed']):
        raise ValueError('reviewed ARM gate did not pass')
    return dict(base,native100_statistics=True,native_manifest_sha256=sha(root/MANIFEST),
        native_arm_evidence_sha256=ARM_SHA,native_recording_sha256=RECORD_SHA)
