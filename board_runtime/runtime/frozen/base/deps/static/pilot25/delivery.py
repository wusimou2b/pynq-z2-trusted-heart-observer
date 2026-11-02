import json
from pathlib import Path
from datetime import datetime
import uuid
from rate25_tools.delivery import digest, local, validate as validate_checked

CHECKED_ZIP_SHA = '06a5cc5e33e1828255a18f728ec8e75ce689f31287de5f06f7c117230e2a6b4b'
CHECKED_MANIFEST_SHA = '3fd7b1a589a7b369b3866a965362d9e9465cdd95e48d07e120d4f3fb1970c5e5'
FLAGS = dict(live_25hz_passed=False, live_50hz_passed=False, auto_beta_effect_passed=False,
             board_ddr_verified=False, limits_frozen=False, run_acceptance_passed=False, v3a_complete=False)
REQUIRED = {'run_v3a25_static.py','README_STATIC25.md','checked/manifest25.json',
            'evidence/arm-budget-audit.json','evidence/arm-pl-audit.json'}
REQUIRED |= {'pilot25/'+name+'.py' for name in ('__init__','delivery','assessment','board','runner')}


def validate(root):
    root = Path(root).resolve()
    doc = json.loads((root/'pilot25-manifest.json').read_text(encoding='utf8'))
    if doc.get('schema') != 'v3a25_static_pilot_bundle_v1' or any(doc.get(k) is not False for k in FLAGS):
        raise ValueError('静止检查包身份／正式门错误')
    if (doc.get('raw_hz'),doc.get('processing_hz'),doc.get('duration_seconds'),doc.get('beta_int')) != (50,25,60,32212255):
        raise ValueError('静止采样参数不符')
    if doc.get('checked_zip_sha256') != CHECKED_ZIP_SHA or digest(root/'checked/manifest25.json') != CHECKED_MANIFEST_SHA:
        raise ValueError('原检查包身份不符')
    files = doc.get('files',{})
    if not REQUIRED <= files.keys(): raise ValueError('静止包缺必要文件身份')
    for name, sha in files.items():
        path = local(root,name)
        if not path.is_file() or digest(path) != sha: raise ValueError('文件缺失或SHA256不符：'+name)
    checked = validate_checked(root/'checked')
    if not {'checked/'+name for name in checked['files']} <= files.keys():
        raise ValueError('旧检查包闭包缺失')
    budget = json.loads((root/'evidence/arm-budget-audit.json').read_text(encoding='utf8'))
    pl = json.loads((root/'evidence/arm-pl-audit.json').read_text(encoding='utf8'))
    if not (budget['stats_recomputed'] and budget['report_vectors_match'] and budget['report_runtime_differences'] == 0
            and pl['board_pl25_replay_verified'] and pl['rows_verified'] == 1701 and pl['public_field_differences'] == 0
            and budget['manifest25_sha256'] == pl['manifest25_sha256'] == CHECKED_MANIFEST_SHA):
        raise ValueError('板端前置证据不完整')
    return doc


def new_output(root, output=None):
    root = Path(root).resolve()
    path = Path(output).resolve() if output is not None else root/'live_results'/(
        'static25-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    if path.is_relative_to(root) and (path == root or path.relative_to(root).parts[0] != 'live_results'):
        raise ValueError('包内输出仅允许live_results新子目录')
    path.mkdir(parents=True,exist_ok=False)
    return path
