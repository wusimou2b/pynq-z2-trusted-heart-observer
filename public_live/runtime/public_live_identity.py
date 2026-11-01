"""Strict public asset identities; no historical recording or hardware imports."""
import json
from pathlib import Path
from public_live_contract import verify_release


def check_runtime(root, release_contract):
    context = verify_release(release_contract)
    if Path(root).resolve(strict=True) != Path(context['runtime_root']):
        raise ValueError('public LIVE runtime root differs from verified release')
    return context


def require_short_receipt(root,release_contract):
    context=check_runtime(root,release_contract)
    receipt=json.loads((Path(root)/'public-short.json').read_text('utf-8'))
    result=receipt.get('result') or {}
    if (receipt.get('schema')!='trusted_heart_public_stage_v1'
            or receipt.get('release_manifest_sha256')!=context['manifest_sha256']
            or receipt.get('error') is not None or result.get('passed') is not True
            or result.get('hardware_accessed') is not False):
        raise ValueError('matching public short identity and natural-exit proof required')
    return receipt


def require_preview_receipt(root,release_contract):
    context=check_runtime(root,release_contract)
    require_short_receipt(root,release_contract)
    receipt=json.loads((Path(root)/'public-preview20.json').read_text('utf-8'))
    result=receipt.get('result') or {}
    if (receipt.get('schema')!='trusted_heart_public_stage_v1'
            or receipt.get('release_manifest_sha256')!=context['manifest_sha256']
            or receipt.get('error') is not None
            or result.get('ownership_qualification_passed') is not True):
        raise ValueError('matching public preview ownership/release proof required')
    from compact_run_video_split import ownership_passed
    if not ownership_passed(result):
        raise ValueError('public preview resource proof differs')
    return receipt


def verify_hardware(directory, release_contract):
    context = verify_release(release_contract)
    bit = context['assets']['bit']
    hwh = context['assets']['hwh']
    selected = Path(bit['path']).parent
    if (Path(directory).resolve(strict=True) != selected
            or Path(hwh['path']).parent != selected
            or Path(bit['path']).name != 'heart_v3b25_main.bit'
            or Path(hwh['path']).name != 'heart_v3b25_main.hwh'):
        raise ValueError('public hardware selection differs from matched pair')
    document = json.loads((selected / 'timeout-release.json').read_text('utf-8'))
    metrics = document['metrics']
    pair = {'heart_v3b25_main.bit': bit['sha256'], 'heart_v3b25_main.hwh': hwh['sha256']}
    if (document.get('schema') != 'timeout_safe_main_spatial_v1'
            or document.get('core_version') != 0x20001
            or document.get('watchdog_cycles') != 2000000
            or document.get('static_validation_passed') is not True
            or document.get('pair') != pair
            or metrics['wns_ns'] < 0 or metrics['whs_ns'] < 0
            or metrics['drc_errors'] or metrics['drc_critical']):
        raise ValueError('public matched hardware release contract differs')
    return dict(files=pair, pair_integrity_verified=True,
                release_manifest_sha256=context['manifest_sha256'],
                validation_scope='public_live_runtime_assets_v1',
                historical_numerical_qualification=False,
                hardware_accessed=False, live_25hz_passed=False,
                full_v3b_acceptance_passed=False)
