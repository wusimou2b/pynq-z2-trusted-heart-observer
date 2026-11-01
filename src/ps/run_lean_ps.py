"""Short original-Bridge exit gate, then a separately confirmed live60 trial."""
import argparse
from functools import partial
import gc
import json
from pathlib import Path
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

sys.dont_write_bytecode = True
if __package__:
    from .lean_ps_guard import verify_package, verify_source, sha, write_new, MANIFEST
    from .joint_startup import replace_attribute
else:
    from lean_ps_guard import verify_package, verify_source, sha, write_new, MANIFEST
    from joint_startup import replace_attribute

ROOT = Path(__file__).resolve().parent


def lean_identity(info, prepared):
    if __package__:
        from .run_native_heart import native_identity_check
    else:
        from run_native_heart import native_identity_check
    lean = info.get('lean_ps') or {}
    return bool(native_identity_check(info, prepared)['passed']
        and lean.get('mode') == 'entry25_original_imports_v1'
        and lean.get('unexpected_modules') == [] and lean.get('hardware_imported') is False)


def run_short(root, source, *, host_check=False, emit=print):
    root, source = Path(root).resolve(), Path(source).resolve()
    checked = verify_package(root)
    prepared = verify_source(root, source, host_check=host_check)
    if any((root/n).exists() for n in ('lean-ps-short-attempt.json', 'lean-ps-short.json', 'lean-ps-short-results.zip')):
        raise FileExistsError('已有短测，保留结果；不覆盖、不自动重试')
    write_new(root/'lean-ps-short-attempt.json', dict(prepared=prepared,
        manifest_sha256=checked['lean_manifest_sha256'], automatic_retry=False, hardware_accessed=False))
    report = dict(schema='v3b25_lean_ps_short_v1', passed=False, error=None,
        prepared=prepared, manifest_sha256=checked['lean_manifest_sha256'],
        ready_info=None, isolation=None, cleanup_complete=False, forced_termination=None,
        exitcode=None, identity_passed=False, configuration_unchanged=False, inputs_unchanged=False,
        host_check=host_check, hardware_accessed=False, formal_steps=0, backend_requests=0,
        ready_timeout_seconds=60, warmup_slots=700, join_seconds=1,
        gc_strategy_changed=False, algorithm_changed=False, strict_realtime_verified=False,
        accuracy_verified=False, board_ddr_verified=False, full_v3b_acceptance_passed=False)
    bridge = None
    before = gc.isenabled(), gc.get_threshold()
    numpy_before = None
    if __package__:
        from .lean_ps_worker import no_hardware, ps_worker
        from .ps_budget_runtime import load_runtime, finish_bridge
    else:
        from lean_ps_worker import no_hardware, ps_worker
        from ps_budget_runtime import load_runtime, finish_bridge
    # Replay helpers are PARENT-only. Spawn loads the cold lean_ps_worker
    # target in a fresh interpreter, never the parent's module dictionary.
    emit('无硬件短退出验证：不放手指、不加载Overlay/采集/视频；原700点和60秒ready。', flush=True)
    try:
        with no_hardware():
            deps = load_runtime(root/'frozen')
            numpy_before = sys.modules['numpy'].geterr()
            bridge = deps.Bridge.__new__(deps.Bridge)
            target = partial(ps_worker, root=root, source=source, host_check=host_check)
            try:
                with replace_attribute(deps.bridge_module, 'worker', target):
                    deps.Bridge.__init__(bridge, 'python_fixed')
                ready = bridge.info()
                report['ready_info'] = ready
                report['identity_passed'] = lean_identity(ready, prepared)
                if not report['identity_passed']:
                    raise ValueError('lean PS ready identity/import scope differs')
            except BaseException as exc:
                # Preserve the original constructor/cancel error before the
                # unchanged close can also report a forced-exit failure.
                report['error'] = dict(type=type(exc).__name__, message=str(exc))
                raise
            finally:
                began = time.monotonic_ns()
                finish_bridge(bridge, report, emit=emit)
                report['close_wall_ns'] = time.monotonic_ns()-began
            report['isolation'] = bridge.info()
    except BaseException as exc:
        report['error'] = report['error'] or dict(type=type(exc).__name__, message=str(exc))
    finally:
        info = report['isolation'] or {}
        report.update(forced_termination=info.get('forced_termination'), exitcode=info.get('exitcode'))
        report['configuration_unchanged'] = bool(before == (gc.isenabled(), gc.get_threshold())
            and numpy_before is not None and numpy_before == sys.modules['numpy'].geterr())
        try:
            verify_package(root)
            after = verify_source(root, source, host_check=host_check)
            if after != prepared:
                raise ValueError('original prepared identity changed during short test')
            report['inputs_unchanged'] = True
        except Exception as exc:
            report['error'] = report['error'] or dict(type=type(exc).__name__, message=str(exc))
        report['passed'] = bool(not report['error'] and report['identity_passed']
            and report['configuration_unchanged'] and report['inputs_unchanged']
            and report['cleanup_complete'] and info.get('forced_termination') is False
            and info.get('exitcode') == 0 and info.get('completed_steps') == info.get('pl_requests') == 0)
        write_new(root/'lean-ps-short.json', report)
        with ZipFile(root/'lean-ps-short-results.zip', 'x', compression=ZIP_DEFLATED) as z:
            z.write(root/'lean-ps-short.json', 'lean-ps-short.json')
    emit('短退出通过：'+str(report['passed'])+'；原forced/exitcode：'
         +str(report['forced_termination'])+'/'+str(report['exitcode']), flush=True)
    emit('短测无硬件，不代替联合60秒或ARM长尾根因证明。失败保留ZIP，不自动重跑。', flush=True)
    return report


def require_short(root, prepared):
    root = Path(root).resolve()
    d = json.loads((root/'lean-ps-short.json').read_text('utf-8'))
    info = d.get('isolation') or {}
    if not (d.get('schema') == 'v3b25_lean_ps_short_v1' and d.get('passed') is True
        and d.get('error') is None and d.get('host_check') is False
        and d.get('forced_termination') is False and d.get('exitcode') == 0
        and d.get('cleanup_complete') is True and d.get('configuration_unchanged') is True
        and d.get('inputs_unchanged') is True and d.get('hardware_accessed') is False
        and d.get('prepared') == prepared and d.get('manifest_sha256') == sha(root/MANIFEST)
        and info.get('forced_termination') is False and info.get('exitcode') == 0
        and info.get('completed_steps') == info.get('pl_requests') == 0
        and lean_identity(info, prepared)):
        raise ValueError('短退出未通过或身份不符；不得启动60秒采集')
    return d


def export_live(root, final):
    root = Path(root)
    write_new(root/'lean-ps-live.json', final)
    with ZipFile(root/'lean-ps-live-results.zip', 'x', compression=ZIP_DEFLATED) as z:
        for n in ('lean-ps-live.json', 'lean-ps-short.json', 'native-heart-results.zip'):
            if (root/n).is_file():
                z.write(root/n, n)


def run_live(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-LEAN-PS60':
        raise ValueError('explicit hardware=True and RUN-LEAN-PS60 required')
    root = ROOT
    source = root.parent/'v3b25 native100 heart video'
    checked = verify_package(root)
    prepared = verify_source(root, source, hardware=True)
    require_short(root, prepared)
    if any((root/n).exists() for n in ('lean-ps-live-attempt.json', 'lean-ps-live-results.zip',
                                      'joint-concurrent-attempt.json', 'native-heart-results.zip')):
        raise FileExistsError('已有实采尝试，保留结果，不覆盖/重跑')
    if __package__:
        from . import run_native_heart as original, native_heart_worker as worker
        from . import browser_heart_guard
        from .lean_ps_worker import start_owner
        from .browser_heart_display import ready_bridge
    else:
        import run_native_heart as original, native_heart_worker as worker, browser_heart_guard
        from lean_ps_worker import start_owner
        from browser_heart_display import ready_bridge
    ready_bridge()
    write_new(root/'lean-ps-live-attempt.json', dict(checked=checked, prepared=prepared,
                                                   automatic_retry=False))
    result = None
    failure = None
    assessed = None
    assess_original = browser_heart_guard.assess_candidate
    def assess(directory, inherited, actual, **kwargs):
        nonlocal assessed
        r = assess_original(directory, inherited, actual, **kwargs)
        isolation = (inherited.get('summary') or {}).get('isolation') or {}
        assessed = dict(passed=lean_identity(isolation, prepared),
                        identity=isolation.get('lean_ps'))
        r['checks']['lean_ps_import_scope'] = assessed['passed']
        r.update(lean_ps=assessed, joint_60s_pilot_completed=all(r['checks'].values()))
        return r
    def validate(requested, *, hardware):
        if Path(requested).resolve() != root:
            raise ValueError('mixed lean PS live root')
        return verify_source(root, source, hardware=hardware)
    print('25/25Hz＋5fps正式60秒：只改变PS加载路径；原算法/700点/保护/收尾不变。', flush=True)
    try:
        with replace_attribute(original, 'ROOT', root), \
             replace_attribute(original, 'validate_prepared', validate), \
             replace_attribute(worker, 'start_owner', partial(start_owner, root=root, source=source)), \
             replace_attribute(browser_heart_guard, 'assess_candidate', assess):
            result = original.run_native60(hardware=True, confirmation='RUN-NATIVE-HEART60')
    except BaseException as exc:
        failure = exc
    identity_error = None
    try:
        verify_package(root)
        if verify_source(root, source, hardware=True) != prepared:
            raise ValueError('prepared identity changed')
    except Exception as exc:
        identity_error = dict(type=type(exc).__name__, message=str(exc))
    final = dict(schema='v3b25_lean_ps_live_v1', prepared=prepared, lean_ps=assessed,
        original_error=dict(type=type(failure).__name__, message=str(failure)) if failure else None,
        identity_error=identity_error, original_zip_sha256=sha(root/'native-heart-results.zip')
            if (root/'native-heart-results.zip').is_file() else None,
        candidate_pilot_completed=bool(result and result.get('joint_60s_pilot_completed')
            and assessed and assessed['passed'] and not failure and not identity_error),
        strict_realtime_verified=False, accuracy_verified=False, board_ddr_verified=False,
        full_v3b_acceptance_passed=False,
        scope='Single lean PS import change; original faults, natural-exit and hardware cleanup preserved')
    try:
        export_live(root, final)
    except BaseException as exc:
        if failure is not None:
            raise failure from exc
        raise
    print('结果：lean-ps-live-results.zip；保留原始结果，不自动重试。', flush=True)
    from IPython.display import FileLink, display
    display(FileLink('lean-ps-live-results.zip'))
    if failure is not None:
        raise failure
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-bundle', action='store_true')
    mode.add_argument('--short', action='store_true')
    args = p.parse_args(argv)
    if args.check_bundle:
        print(json.dumps(verify_package(ROOT), ensure_ascii=False))
        return 0
    r = run_short(ROOT, ROOT.parent/'v3b25 native100 heart video')
    return 0 if r['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
