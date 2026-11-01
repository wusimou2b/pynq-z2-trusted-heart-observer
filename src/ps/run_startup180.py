"""Bounded preparation-only 180s candidate; frozen source and real clocks are intact."""
import argparse
from contextlib import contextmanager
import hashlib
import importlib
import json
from pathlib import Path
import sys
import time
from types import FunctionType
import zipfile
sys.dont_write_bytecode = True

if __package__:
    from .joint_owner import require_board
    from .driver_preload import write_new
    from .joint_startup import replace_attribute
else:
    from joint_owner import require_board
    from driver_preload import write_new
    from joint_startup import replace_attribute

ROOT = Path(__file__).resolve().parent
MANIFEST = 'startup180-manifest.json'
FILES = {'run_startup180.py', 'README_STARTUP180.md'}
PARENT_SHA = '12667a4407bce347be7e1a867bce36d1e5791d714338113903a62c2e070d51b5'
DISPLAY_SHA = 'e9f5d69706e93d3ce9db0dbf50cf6bc2ac02a9ce40af3612c7172dfeb17c93f4'
OLD_MESSAGE = '所有者启动超过90秒，请求停止并等待真实清理'
NEW_MESSAGE = '所有者启动超过180秒，请求停止并等待真实清理'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def notebook_hash(path):
    nb = json.loads(Path(path).read_text('utf-8'))
    cells = [''.join(c['source']) for c in nb['cells'] if c['cell_type'] == 'code']
    return hashlib.sha256(json.dumps(cells, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def with_startup180(original):
    """Clone precisely two literals; reuse original globals so later owner hooks stay live."""
    constants = original.__code__.co_consts
    limits = [i for i,x in enumerate(constants) if type(x) is int and x == 90]
    messages = [i for i,x in enumerate(constants) if type(x) is str and x == OLD_MESSAGE]
    if len(limits) != 1 or len(messages) != 1:
        raise ValueError('reviewed parent startup constant contract changed; no hardware started')
    changed = list(constants)
    changed[limits[0]], changed[messages[0]] = 180, NEW_MESSAGE
    result = FunctionType(original.__code__.replace(co_consts=tuple(changed)), original.__globals__,
        original.__name__, original.__defaults__, original.__closure__)
    result.__kwdefaults__ = dict(original.__kwdefaults__) if original.__kwdefaults__ is not None else None
    result.__qualname__, result.__module__, result.__doc__ = original.__qualname__, original.__module__, original.__doc__
    return result


def load_display(root):
    frozen = Path(root).resolve() / 'frozen'
    source = frozen / 'base/effective25/display.py'
    if source.is_symlink() or sha(source) != DISPLAY_SHA:
        raise ValueError('frozen parent source changed')
    if str(frozen) not in sys.path: sys.path.insert(0, str(frozen))
    guard = importlib.import_module('entry25_guard')
    if Path(guard.__file__).resolve().parent != frozen: raise ValueError('mixed entry25_guard; use a fresh notebook')
    guard.activate(frozen)
    display = importlib.import_module('effective25.display')
    if Path(display.__file__).resolve() != source:
        raise ValueError('mixed parent display module; use a fresh notebook')
    return display


@contextmanager
def install_startup180(root):
    display = load_display(root)
    original = display.run
    candidate = with_startup180(original)
    real_clock = time.monotonic
    audit = dict(startup_timeout_seconds=180, reference_startup_timeout_seconds=90,
        parent_run_calls=0, parent_bytecode_unchanged=candidate.__code__.co_code == original.__code__.co_code,
        shared_original_globals=candidate.__globals__ is original.__globals__,
        real_clock_unchanged=True, frozen_parent_sha256=DISPLAY_SHA)
    def run(*args, **kwargs):
        audit['parent_run_calls'] += 1
        return candidate(*args, **kwargs)
    try:
        with replace_attribute(display, 'run', run): yield audit
    finally: audit['real_clock_unchanged'] = time.monotonic is real_clock


def verify_package(root):
    root = Path(root).resolve()
    path = root / MANIFEST
    if path.is_symlink(): raise ValueError('startup180 manifest symlink')
    doc = json.loads(path.read_text('utf-8'))
    if (doc.get('schema') != 'v3b25_startup180_package_v1' or set(doc.get('files',{})) != FILES
        or doc.get('parent_manifest_sha256') != PARENT_SHA
        or sha(root / 'driver-preload-manifest.json') != PARENT_SHA
        or (doc.get('startup_timeout_seconds'), doc.get('reference_startup_timeout_seconds'),
            doc.get('ps_warmup_timeout_seconds'), doc.get('warmup_slots'), doc.get('formal_seconds'),
            doc.get('raw_hz'), doc.get('processing_hz'), doc.get('video_target_fps')) != (180,90,60,700,60,25,25,5)
        or doc.get('board_tested') is not False):
        raise ValueError('startup180 package scope changed')
    for name,expected in doc['files'].items():
        if (root/name).is_symlink() or sha(root/name) != expected: raise ValueError('startup180 file changed: '+name)
    nb = root / 'Startup180Joint60.ipynb'
    if nb.is_symlink() or notebook_hash(nb) != doc.get('notebook_code_sha256'):
        raise ValueError('startup180 notebook executable changed')
    source = root / 'frozen/base/effective25/display.py'
    if source.is_symlink() or sha(source) != DISPLAY_SHA: raise ValueError('parent display source identity changed')
    if __package__:
        from .run_driver_preload import verify_candidate
        from .iic_handoff_build import verify_build
    else:
        from run_driver_preload import verify_candidate
        from iic_handoff_build import verify_build
    verify_candidate(root); build = verify_build(root)
    return dict(bundle_validated=True, startup180_manifest_sha256=sha(path),
        startup_timeout_seconds=180, reference_startup_timeout_seconds=90,
        ps_warmup_timeout_seconds=60, warmup_slots=700, formal_seconds=60,
        native_library_sha256=build['library_sha256'], hardware_accessed=False)


def run_joint60(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-STARTUP180-60':
        raise ValueError('requires hardware=True and RUN-STARTUP180-60')
    require_board(); root = ROOT
    attempt, archive = root/'startup180-attempt.json', root/'startup180-results.zip'
    if any(p.exists() for p in (attempt,archive,root/'driver-preload-attempt.json',
        root/'iic-handoff-attempt.json',root/'frozen/live_results/joint-concurrent5-static60')):
        raise FileExistsError('existing attempt/results; preserve, no retry')
    before = verify_package(root)
    if __package__: from . import run_driver_preload as original
    else: import run_driver_preload as original
    write_new(attempt, dict(schema='v3b25_startup180_attempt_v1', automatic_retry=False,
        manifest_sha256=before['startup180_manifest_sha256'], startup_timeout_seconds=180,
        reference_startup_timeout_seconds=90))
    print('本次真实总启动等待上限180秒；旧继承提示/清单中的90秒仅为冻结参考。', flush=True)
    print('PS预热仍最多60秒/700点，正式共同60秒、25/25Hz、5fps、IIC50ms及所有实时/收尾门不变。', flush=True)
    old, budget, errors = {}, {}, []
    try:
        with install_startup180(root) as budget:
            old = original.run_joint60(hardware=True, confirmation='RUN-DRIVER-PRELOAD60')
    except BaseException as exc: errors.append(dict(stage='inherited_entry', type=type(exc).__name__, message=str(exc)))
    unchanged = False
    try: unchanged = verify_package(root) == before
    except BaseException as exc: errors.append(dict(stage='postrun_identity', type=type(exc).__name__, message=str(exc)))
    checks = dict(original_joint=old.get('driver_preload_joint60_completed') is True,
        correct_parent_entry=budget.get('parent_run_calls') == 1,
        budget_only=budget.get('parent_bytecode_unchanged') is True and budget.get('shared_original_globals') is True
            and budget.get('real_clock_unchanged') is True,
        inputs_unchanged=unchanged, no_wrapper_error=not errors)
    result = dict(schema='v3b25_startup180_joint60_v1', checks=checks,
        startup180_joint60_completed=all(checks.values()), startup_timeout_seconds=180,
        reference_startup_timeout_seconds=90, ps_warmup_timeout_seconds=60, warmup_slots=700,
        formal_seconds=60, raw_hz=25, processing_hz=25, video_target_fps=5,
        parent_budget=budget, inherited_report=old, errors=errors,
        live_25hz_passed=False, live_50hz_passed=False, board_ddr_verified=False,
        full_v3b_acceptance_passed=False, accuracy_verified=False,
        scope='Preparation wait budget only; legacy 90s labels are reference, all steady-state gates retained')
    write_new(root/'startup180-result.json', result)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in ('driver-preload-results.zip','startup180-attempt.json','startup180-result.json',MANIFEST):
            if (root/name).is_file(): z.write(root/name,name)
    print('180秒启动候选共同60秒小试完整：',result['startup180_joint60_completed'],'；不是完整验收。',flush=True)
    print('结果ZIP：',archive,flush=True)
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle',action='store_true',required=True)
    parser.parse_args(); print(json.dumps(verify_package(ROOT),ensure_ascii=False))
