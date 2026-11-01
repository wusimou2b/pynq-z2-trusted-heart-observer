"""Movable, local-only identities. Working notebooks are intentionally untracked."""
import hashlib
import json
from pathlib import Path, PurePosixPath

FLAGS = dict(hardware_loaded=False, board_tested=False, live_25hz_passed=False, live_50hz_passed=False,
             auto_beta_effect_passed=False, board_ddr_verified=False, limits_frozen=False,
             run_acceptance_passed=False, v3a_complete=False)
BASE_ZIP_SHA = '24cb71ea606cdbc728a106f10b1354a4cea05790bb018e86baab2a9f780b922f'
BASE_MANIFEST_SHA = 'f9982dce7124067260bf6a9a1e8b8f73a518448e8e75665c5340ca111d1471a5'
REQUIRED = {'run_v3a25.py', 'README_25HZ.md', 'base/manifest.json', 'base/live-manifest.json',
            'base/heart_v3a.bit', 'base/heart_v3a.hwh', 'peak_chain.py', 'peak_timing.py',
            'v3a_25hz_live/bridge.py', 'v3a_25hz_live/safety.py',
            'inputs/cases.json', 'inputs/vectors.json', 'inputs/original_raw.csv',
            'provenance25/previous-verification.json',
            'rate25_tools/__init__.py', 'rate25_tools/delivery.py', 'rate25_tools/data.py'}
REQUIRED |= {'v3a_rate25/'+name+'.py' for name in ('__init__','policy','frontend','state','benefit','chain')}
REQUIRED |= {'rate25_tools/budget.py', 'rate25_tools/reporting.py'}
REQUIRED |= {'rate25_tools/replay.py', 'rate25_tools/hardware.py'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(root, name):
    root = Path(root).resolve()
    posix = PurePosixPath(name)
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or posix.is_absolute() or '..' in posix.parts:
        raise ValueError('包内路径非法')
    path = (root/name).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('包内路径逃逸')
    return path


def validate(root):
    root = Path(root).resolve()
    document = json.loads((root/'manifest25.json').read_text(encoding='utf8'))
    if document.get('schema') != 'v3a25_checks_bundle_v1' or any(document.get(k) is not False for k in FLAGS):
        raise ValueError('25Hz检查包schema／未验门不符')
    if (document.get('raw_hz'), document.get('processing_hz'), document.get('beta_int')) != (50,25,32212255):
        raise ValueError('采样率或固定参数不符')
    files = document.get('files', {})
    if not REQUIRED <= files.keys(): raise ValueError('25Hz检查包缺必要文件身份')
    if document.get('base_zip_sha256') != BASE_ZIP_SHA or digest(root/'base/manifest.json') != BASE_MANIFEST_SHA:
        raise ValueError('原交付身份不符')
    for name, sha in files.items():
        path = local(root, name)
        if not path.is_file() or digest(path) != sha:
            raise ValueError('文件缺失或SHA256不符：'+name)
    from heart_v3a.live_delivery import validate_live_bundle
    validate_live_bundle(root/'base')
    return document
