"""缓存显示＋60秒静止采集。默认只验包；硬件仅由Notebook显式启动。"""
import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import platform
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
MANIFEST = 'cached-live25-manifest.json'
DISPLAY_SHA = '20578e2920adfe6f72d5c1c74af58c7fafa09aab89dab2e16b979362d8f0124a'
CANDIDATE_SHA = '85e9a0d793c20c4a8f42c6460acaf17cc64da3b56013ef7ee847ea7345c901de'
ADDON_FILES = {'run_v3a25_cached_live.py', 'v3a25_cached_display.py'}
FLAGS = dict.fromkeys(('live_25hz_passed', 'live_50hz_passed', 'auto_beta_effect_passed',
    'board_ddr_verified', 'limits_frozen', 'run_acceptance_passed', 'v3a_complete'), False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(root):
    """Only stdlib and reads: reject altered predecessors before importing them."""
    root = Path(root).resolve()
    tracked = {}
    def check(name, expected):
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha(path) != expected:
            raise ValueError('文件缺失／身份不符：'+name+'；不要修改manifest或启动采集')
        tracked[str(path)] = expected
    check('display25-manifest.json', DISPLAY_SHA)
    original = json.loads((root/'display25-manifest.json').read_text(encoding='utf8'))
    for name, digest in original['files'].items(): check(name, digest)
    check('v3a25_cached_display.py', CANDIDATE_SHA)
    if not (root/MANIFEST).is_file(): raise ValueError('缺少附加清单：'+MANIFEST)
    check(MANIFEST, sha(root/MANIFEST))
    addon = json.loads((root/MANIFEST).read_text(encoding='utf8'))
    if (addon.get('schema') != 'v3a25_cached_live_addon_v1'
            or any(addon.get(k) is not False for k in FLAGS)
            or addon.get('display25_manifest_sha256') != DISPLAY_SHA
            or addon.get('candidate_sha256') != CANDIDATE_SHA
            or (addon.get('raw_hz'), addon.get('processing_hz'), addon.get('duration_seconds')) != (50,25,60)
            or set(addon.get('files', {})) != ADDON_FILES):
        raise ValueError('附加清单身份／范围不符')
    for name, digest in addon['files'].items(): check(name, digest)
    return dict(root=root, tracked_hashes=tracked, candidate_sha256=CANDIDATE_SHA,
                addon_manifest_sha256=sha(root/MANIFEST))


def changed_files(context):
    changed = []
    for name, digest in context['tracked_hashes'].items():
        try:
            if sha(name) != digest: changed.append(name)
        except OSError: changed.append(name)
    return changed


def require_notebook():
    try:
        from IPython import get_ipython
    except ImportError as exc:
        raise RuntimeError('需要板端Notebook；不要在此处安装依赖') from exc
    shell = get_ipython()
    if shell is None or getattr(shell, 'kernel', None) is None:
        raise RuntimeError('请在新Notebook单元直接调用，不要用终端或subprocess采集')


def prepare_runtime(context):
    root = context['root']
    prefixes = ('display25', 'pilot25', 'heart_v2', 'heart_v3a', 'v3a_25hz_live',
                'v3a_rate25', 'rate25_tools')
    singles = ('peak_chain', 'peak_timing', 'heart_axi_live', 'heart_axi_capture_50hz',
               'run_v3a25_display', 'v3a25_cached_display')
    for name, module in tuple(sys.modules.items()):
        if name.split('.')[0] in prefixes or name in singles:
            file = getattr(module, '__file__', None)
            if file and not Path(file).resolve().is_relative_to(root):
                raise ValueError('旧内核串包，请关闭旧采集后新建Notebook／重启内核：'+name)
    if changed_files(context): raise ValueError('校验后文件改变，停止')
    for path in reversed((root, root/'static', root/'static/checked', root/'static/checked/base')):
        sys.path.insert(0, str(path))
    delivery = importlib.import_module('display25.delivery')
    delivery.validate(root)
    delivery.verify_imports(root)
    spec = importlib.util.spec_from_file_location('_cached_live_builder', root/'v3a25_cached_display.py')
    candidate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(candidate)
    return candidate


class CachedRenderer:
    """Only render supplied presentation; LiveView25 remains the permission owner."""
    def __init__(self, publish, builder, *, clock=time):
        self.publish, self.builder, self.clock = publish, builder, clock
        self._attempts = []

    def __call__(self, snapshot, value):
        latest = snapshot.latest
        frame = latest.runtime.frame if latest is not None else None
        safety = snapshot.counts.get('raw_safety', {})
        trace = dict(at_ns=self.clock.monotonic_ns(), completed_ns=None, success=False, error='',
            sequence=frame.sequence if frame else None,
            read_completed_ns=latest.saved.record.read_completed_ns if latest else None,
            state=snapshot.state, faulted=snapshot.fault is not None,
            frame_allowed=frame.output_allowed if frame else False, frame_bpm=frame.bpm if frame else None,
            slot_generation=latest.slot.generation if latest else None,
            safety_generation=safety.get('generation'), contact_ready=safety.get('contact_ready', False),
            bpm_text=value['bpm_text'], historical=value['historical'], build_ns=None, publish_ns=None)
        start = self.clock.monotonic_ns()
        split = None
        try:
            markup = self.builder.build_html(snapshot, value)
            split = self.clock.monotonic_ns()
            trace['build_ns'] = split-start
            self.publish(markup)
            trace['success'] = True
        except BaseException as exc:
            trace['error'] = str(exc) or type(exc).__name__
            raise
        finally:
            end = self.clock.monotonic_ns()
            trace['completed_ns'] = end
            if split is None: trace['build_ns'] = end-start
            else: trace['publish_ns'] = end-split
            self._attempts.append(trace)

    def metrics(self):
        return dict(attempts=[dict(item) for item in self._attempts], renderer='cached_svg_v1',
                    cache=self.builder.cache_stats())


def run(root, output=None, *, hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    require_notebook()
    context = validate(root)
    candidate = prepare_runtime(context)
    root = context['root']
    from display25.delivery import new_output
    from display25.runner import execute, _stop, _error
    from display25.render import ipython_publisher
    from display25.assessment import assess
    from heart_v3a.live.contracts import LiveSnapshot
    from v3a_25hz_live.view import LiveView25, presentation25
    from pilot25.board import prepare
    directory = new_output(root, output if output is not None else
                           root/'live_results'/('cached-display25-'+uuid.uuid4().hex[:12]))
    report = dict(schema='v3a25_cached_display_run_v1', **FLAGS, cached_display_pilot_completed=False,
        display_pilot_completed=False, display25_manifest_sha256=DISPLAY_SHA,
        candidate_sha256=CANDIDATE_SHA, script_sha256=sha(root/'run_v3a25_cached_live.py'),
        addon_manifest_sha256=context['addon_manifest_sha256'], python=sys.version, machine=platform.machine(),
        raw_hz=50, processing_hz=25, duration_seconds=60., protocol='static', mode='baseline',
        error=None, summary=None, backend_fault='', capture_directory=str(directory/'capture'),
        browser_display_measured=False, display_measurement_scope='kernel_publish',
        inputs_unchanged=False, changed_files=[], renderer='cached_svg_v1')
    session = renderer = None
    execute_entered = False
    print('缓存显示联合小试：请放稳手指，只运行本单元；加载原Overlay，DDR仍未验收。', flush=True)
    print('独立PS预热最长60秒另计；正式静止采集＋显示60秒，不同时绘图／复制文件。', flush=True)
    try:
        renderer = CachedRenderer(ipython_publisher(), candidate.CachedSvgBuilder())
        initial = LiveSnapshot('preflight', None, None, (), {})
        value = presentation25(initial, time.monotonic_ns())
        value['reason_cn'] = '正在预热／等待正式采集；此时不显示心率'
        renderer(initial, value)
        session = prepare(root/'static', directory/'capture', hardware=True)
        session._assess_summary = assess
        session._preflight.update(display25_manifest_sha256=DISPLAY_SHA,
            cached_display_candidate_sha256=CANDIDATE_SHA,
            cached_display_addon_manifest_sha256=context['addon_manifest_sha256'])
        view = LiveView25(session.snapshot, renderer)
        execute_entered = True
        summary, error = execute(session, view, renderer)
        report.update(summary=summary, error=error, backend_fault=getattr(session.backend, '_fault', ''))
    except (Exception, KeyboardInterrupt) as exc:
        report['error'] = _error(exc, 'execution' if execute_entered else 'preflight')
        if session is not None:
            report['backend_fault'] = getattr(session.backend, '_fault', '')
            try:
                report['exception_cleanup'], report['cleanup_error'] = _stop(session)
            except (Exception, KeyboardInterrupt) as cleanup_exc:
                report['cleanup_error'] = _error(cleanup_exc, 'cleanup')
    finally:
        report['display_attempts'] = renderer.metrics() if renderer is not None else None
        report['changed_files'] = changed_files(context)
        report['inputs_unchanged'] = not report['changed_files']
        if not report['inputs_unchanged']:
            report['error'] = report['error'] or _error(ValueError('运行期间输入／产品文件改变'), 'integrity')
        completed = bool(report['summary'] and report['summary'].get('display_pilot_completed')
                         and report['error'] is None and report['inputs_unchanged'])
        report['display_pilot_completed'] = report['cached_display_pilot_completed'] = completed
        with (directory/'run_cached_display25.json').open('x', encoding='utf8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print('结果目录：'+str(directory), flush=True)
    print('缓存显示并发基础检查：'+str(completed)+'；不是完整实时／准确率／DDR验收。', flush=True)
    if report['error']:
        print('故障已保存，请回传文件；不要自动重试。'+str(report['error']), flush=True)
    from IPython.display import FileLink, display
    for path in (directory/'run_cached_display25.json', *(directory/'capture'/name
            for name in ('raw.csv', 'results.csv', 'events.jsonl', 'summary.json'))):
        if path.is_file():
            try: display(FileLink(str(path.relative_to(Path.cwd()))))
            except ValueError: print(str(path), flush=True)
    return report


def run_cached_display60(*, hardware=False, output=None):
    return run(ROOT, output, hardware=hardware)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle', action='store_true')
    parser.parse_args()
    validate(ROOT)
    print(json.dumps(dict(bundle_validated=True, **FLAGS, hardware_loaded=False,
        raw_hz=50, processing_hz=25, entry='notebook_cached_display60', renderer='cached_svg_v1')))
    return 0


if __name__ == '__main__': raise SystemExit(main())
