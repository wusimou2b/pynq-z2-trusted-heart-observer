"""Manual driver-preload candidate; all original joint gates remain in force."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile
sys.dont_write_bytecode = True

if __package__:
    from .joint_owner import require_board
    from .joint_startup import replace_attribute
    from .driver_preload import write_new
else:
    from joint_owner import require_board
    from joint_startup import replace_attribute
    from driver_preload import write_new

ROOT = Path(__file__).resolve().parent
MANIFEST = 'driver-preload-manifest.json'
PREVIOUS_SHA = 'f17686d50b36f730554ec658b8d01e4b12e9e78a73a081590d05eb5033ff95a4'
FILES = {'driver_preload.py', 'run_driver_preload.py', 'README_DRIVER_PRELOAD.md'}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def notebook_hash(path):
    nb = json.loads(Path(path).read_text('utf-8'))
    cells = [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']
    return hashlib.sha256(json.dumps(cells, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def verify_candidate(root):
    root = Path(root).resolve()
    if (root / MANIFEST).is_symlink(): raise ValueError('preload manifest symlink')
    doc = json.loads((root / MANIFEST).read_text('utf-8'))
    if (doc.get('schema') != 'v3b25_driver_preload_package_v1' or set(doc.get('files', {})) != FILES
        or doc.get('original_iic_manifest_sha256') != PREVIOUS_SHA
        or sha(root / 'iic-handoff-manifest.json') != PREVIOUS_SHA
        or (doc.get('raw_hz'), doc.get('processing_hz'), doc.get('video_target_fps'),
            doc.get('formal_seconds'), doc.get('startup_timeout_seconds'), doc.get('warmup_slots')) != (25, 25, 5, 60, 90, 700)
        or doc.get('hardware_verified') is not False):
        raise ValueError('preload candidate scope/identity mismatch')
    for name, expected in doc['files'].items():
        if (root / name).is_symlink() or sha(root / name) != expected:
            raise ValueError('preload source changed: ' + name)
    nb = root / 'DriverPreload60.ipynb'
    if nb.is_symlink() or notebook_hash(nb) != doc.get('notebook_code_sha256'):
        raise ValueError('preload executable notebook changed')
    return dict(candidate_validated=True, driver_preload_manifest_sha256=sha(root / MANIFEST),
        hardware_accessed=False, startup_timeout_seconds=90, warmup_slots=700)


def run_joint60(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-DRIVER-PRELOAD60':
        raise ValueError('requires hardware=True and RUN-DRIVER-PRELOAD60')
    require_board(); root = ROOT
    attempt, archive = root / 'driver-preload-attempt.json', root / 'driver-preload-results.zip'
    directory = root / 'frozen/live_results/joint-concurrent5-static60'
    if any(p.exists() for p in (attempt, archive, root / 'iic-handoff-attempt.json',
                               root / 'iic-handoff-results.zip', directory)):
        raise FileExistsError('existing attempt/results; preserve, no retry')
    before = verify_candidate(root)
    if __package__:
        from . import run_iic_handoff as original, iic_handoff_worker as original_worker
        from .driver_preload import start_owner
    else:
        import run_iic_handoff as original, iic_handoff_worker as original_worker
        from driver_preload import start_owner
    write_new(attempt, dict(schema='v3b25_driver_preload_attempt_v1', automatic_retry=False,
        manifest_sha256=before['driver_preload_manifest_sha256']))
    print('驱动提前加载候选：只有同一硬件所有者内的导入与算法初始化重叠。', flush=True)
    print('原90秒/700点预热/25,25Hz/5fps/共同60秒/IIC50ms/GC/退出门不改；失败保存不重试。', flush=True)
    old, preload, errors = {}, {}, []
    try:
        with replace_attribute(original_worker, 'start_owner', start_owner):
            old = original.run_joint60(hardware=True, confirmation='RUN-IIC-HANDOFF60')
    except BaseException as exc: errors.append(dict(stage='original_entry', type=type(exc).__name__, message=str(exc)))
    try: preload = json.loads((directory / 'owner_driver_preload.json').read_text('utf-8'))
    except Exception as exc: errors.append(dict(stage='driver_preload_report', type=type(exc).__name__, message=str(exc)))
    unchanged = False
    try: unchanged = verify_candidate(root) == before
    except BaseException as exc: errors.append(dict(stage='candidate_postcheck', type=type(exc).__name__, message=str(exc)))
    checks = dict(original_joint=old.get('iic_handoff_joint60_completed') is True,
        driver_lifecycle=preload.get('lifecycle_complete') is True,
        inputs_unchanged=unchanged, no_wrapper_error=not errors)
    result = dict(schema='v3b25_driver_preload_joint60_v1', checks=checks,
        driver_preload_joint60_completed=all(checks.values()), original_joint_report=old,
        driver_preload=preload, errors=errors, candidate_inputs_unchanged=unchanged,
        actual_bootstrap_overlap_observed=preload.get('bootstrap_overlap_ns', 0) > 0,
        startup_speed_improved_verified=False, full_v3b_acceptance_passed=False,
        live_25hz_passed=False, board_ddr_verified=False, accuracy_verified=False,
        scope='Startup import overlap only; retain original run, cleanup and acceptance gates')
    write_new(root / 'driver-preload-result.json', result)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for name in ('iic-handoff-results.zip', 'driver-preload-attempt.json', 'driver-preload-result.json', MANIFEST):
            if (root / name).is_file(): z.write(root / name, name)
        if (directory / 'owner_driver_preload.json').is_file():
            z.write(directory / 'owner_driver_preload.json', 'owner_driver_preload.json')
    print('驱动提前加载联合小试完整：', result['driver_preload_joint60_completed'], '；不是完整验收。', flush=True)
    print('结果ZIP：', archive, flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle', action='store_true', required=True)
    parser.parse_args()
    checked = verify_candidate(ROOT)
    if __package__: from .iic_handoff_build import verify_build
    else: from iic_handoff_build import verify_build
    build = verify_build(ROOT)
    checked['native_library_sha256'] = build['library_sha256']
    print(json.dumps(checked, ensure_ascii=False))
