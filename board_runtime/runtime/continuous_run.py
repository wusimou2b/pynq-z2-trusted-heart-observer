"""Manual continuous Notebook parent; no kernel interrupts or owner termination."""
from collections import deque
import json
import multiprocessing as mp
from pathlib import Path
import sys
import time
import uuid
from zipfile import ZipFile, ZIP_DEFLATED

sys.dont_write_bytecode = True
if __package__:
    from .continuous_control import StopControl, assess_manual, audit_artifacts
else:
    from continuous_control import StopControl, assess_manual, audit_artifacts

ROOT = Path(__file__).resolve().parent
_PREPARED = None
_USED = False


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def describe(exc, stage):
    return dict(stage=stage, type=type(exc).__name__, message=str(exc) or type(exc).__name__)


def prepare():
    """Return to the kernel so the unchanged browser clock handshake can finish."""
    global _PREPARED
    if _PREPARED is not None:
        raise RuntimeError('already prepared; preserve the first display, no restart')
    if __package__:
        from .continuous_guard import verify_package
        from .lean_ps_guard import verify_source
        from .run_lean_ps import require_short
        from .browser_heart_display import BrowserBridge
    else:
        from continuous_guard import verify_package
        from lean_ps_guard import verify_source
        from run_lean_ps import require_short
        from browser_heart_display import BrowserBridge
    checked = verify_package(ROOT)
    source = ROOT.parent/'v3b25 native100 heart video'
    prepared = verify_source(ROOT, source)
    require_short(ROOT, prepared)
    from IPython import get_ipython
    from IPython.display import HTML, Javascript, display
    shell = get_ipython()
    if getattr(shell, 'kernel', None) is None:
        raise RuntimeError('requires classic Jupyter Notebook')
    bridge = BrowserBridge()
    token = uuid.uuid4().hex
    control = StopControl(ROOT/'continuous-control', token)
    target = 'continuous25-'+token
    shell.kernel.comm_manager.register_target(target, bridge.opened)
    _PREPARED = dict(bridge=bridge, control=control, checked=checked, prepared=prepared)
    markup = ('<div id="'+target+'" style="max-width:1000px;font:14px sans-serif">'
        '<p data-ready>正在连接浏览器绘图；等待绿色就绪提示后再启动</p>'
        '<button data-stop style="padding:10px 16px">正常停止并导出</button>'
        '<p data-stop-status>准备中；未启动采集</p><pre data-status>心率：N/A</pre>'
        '<p data-note>等待数据</p>'
        '<p>● 原始去直流　● 两点均值　● NLMS候选　● 联合保护输出</p>'
        '<canvas width="960" height="280" style="width:100%;border:1px solid #dde2e8"></canvas>'
        '<p>25/25Hz＋5fps；首轮约3分钟后点击正常停止。暂停/断连即历史，非医疗用途。</p></div>')
    code = (ROOT/'browser_heart_client.js').read_text('utf-8')+'\n'+(ROOT/'continuous_client.js').read_text('utf-8')
    options = dict(id=target, target=target, token=token, controlPath='continuous-control')
    display(HTML(markup))
    display(Javascript(code+'\nContinuousControl.boot('+json.dumps(options)+');'))
    return dict(prepared=True, hardware_accessed=False, token=token)


def drive_owner(start, mailbox, control, stop, manual, metrics_ready, view, directory,
                *, renderer_metrics, clock=time, emit=print):
    """Same original parent stop/metrics/join handshake, with a scoped stop-file poll."""
    process = None
    last_snapshot = mailbox.snapshot()
    report = dict(error=None, owner_pid=None, owner_exitcode=None, cancelled_before_owner=False)
    def provider():
        nonlocal last_snapshot
        mailbox.touch()
        control.poll(stop, manual)
        last_snapshot = mailbox.snapshot(alive=process is None or process.is_alive())
        return last_snapshot
    view.provider = provider
    initial_ok = False
    try:
        control.mark('starting')
        control.poll(stop, manual, force=True)
        if manual.is_set():
            report['cancelled_before_owner'] = True
            return report
        if not view.refresh():
            raise RuntimeError('initial N/A publication failed: '+view.metrics()['error'])
        initial_ok = True
        if manual.is_set():
            report['cancelled_before_owner'] = True
            return report
        process = start()
        report['owner_pid'] = process.pid
        started = clock.monotonic()
        announced = False
        while process.is_alive():
            snap = provider()
            if manual.is_set():
                break
            if snap.fault is not None:
                raise RuntimeError(snap.fault.reason)
            if snap.state == 'running' and not announced:
                announced = True
                control.mark('running')
                emit('预热完成：进入持续25/25Hz＋5fps；首轮约3分钟后点击上方“正常停止并导出”。', flush=True)
            if snap.state not in ('preflight','running'):
                break
            if not announced and clock.monotonic()-started > 180:
                raise TimeoutError('所有者启动超过180秒，请求停止并等待真实清理')
            view.refresh()
            if view.metrics()['display_errors']:
                raise RuntimeError(view.metrics()['error'])
            clock.sleep(.02)
        if not process.is_alive() and process.exitcode != 0:
            raise RuntimeError('owner exited abnormally; cleanup not confirmed')
    except (Exception, KeyboardInterrupt) as exc:
        report['error'] = describe(exc, 'display_or_owner')
    finally:
        stop.set()
        try:
            control.mark('stopping')
        except BaseException as exc:
            report['error'] = report['error'] or describe(exc, 'stop_state')
        view.provider = lambda:last_snapshot
        clear = False
        if initial_ok:
            try:
                clear = view.finish()
            except (Exception, KeyboardInterrupt) as exc:
                report['error'] = report['error'] or describe(exc, 'final_clear')
        try:
            metrics = dict(view.metrics(), **renderer_metrics(), final_clear_published=clear,
                           loop_error=report['error'], measurement_scope='kernel_publish')
            write_new(Path(directory)/'display_metrics.json', metrics)
        except BaseException as exc:
            report['error'] = report['error'] or describe(exc, 'write_display_metrics')
        finally:
            metrics_ready.set()
        if process is not None:
            notice = clock.monotonic()
            while process.is_alive():
                try:
                    process.join(.1)
                except KeyboardInterrupt as exc:
                    report['error'] = report['error'] or describe(exc, 'wait_cleanup')
                if process.is_alive() and clock.monotonic()-notice >= 5:
                    try:
                        control.mark('shutdown_incomplete')
                        emit('停止未完成：保留所有者、缓冲和租约，不强杀，不启动其它入口。', flush=True)
                    except BaseException as exc:
                        report['error'] = report['error'] or describe(exc, 'cleanup_status')
                    notice = clock.monotonic()
                clock.sleep(.01)
            report['owner_exitcode'] = process.exitcode
            report['owner_exit_observed_ns'] = time.monotonic_ns()
            process.close()
        if initial_ok and not clear:
            report['error'] = report['error'] or describe(RuntimeError('final N/A was not published'), 'final_clear')
    return report


def streaming_renderer(bridge, directory):
    if __package__:
        from .browser_heart_display import BrowserRenderer
    else:
        from browser_heart_display import BrowserRenderer
    class StreamingRenderer(BrowserRenderer):
        def __init__(self):
            super().__init__(bridge)
            # Original view retains500 refresh samples, at most two render
            # attempts per sample plus the final clear. Keep their evidence.
            self._attempts = deque(maxlen=1024)
            self.total = 0
            self.sink = (Path(directory)/'display_attempts.jsonl').open('x', encoding='utf-8')
        def __call__(self, snapshot, value):
            try:
                super().__call__(snapshot, value)
            finally:
                if self._attempts:
                    self.sink.write(json.dumps(self._attempts[-1], ensure_ascii=False, allow_nan=False)+'\n')
                    self.sink.flush()
                    self.total += 1
        def metrics(self):
            return dict(super().metrics(), attempts_total=self.total, attempts_capacity=1024,
                        full_attempts_journal='display_attempts.jsonl')
    return StreamingRenderer()


def export_result(root, result, control):
    root = Path(root)
    archive = root/'continuous-results.zip'
    try:
        write_new(root/'continuous-result.json', result)
        # Only our stopped-session tree, not arbitrary notebooks or earlier results.
        files = [root/'continuous-result.json', root/'continuous-attempt.json',
                 root/'lean-ps-short.json', root/'continuous-manifest.json', control.directory/'state.json']
        if (control.directory/'request.json').is_file():
            files.append(control.directory/'request.json')
        files.extend(p for p in sorted((root/'continuous-results').rglob('*')) if p.is_file())
        with ZipFile(archive, 'x', compression=ZIP_DEFLATED) as z:
            for path in files:
                if path.is_file():
                    z.write(path, path.relative_to(root).as_posix())
        control.finish(result, archive)
    except BaseException:
        control.mark('export_failed')
        raise
    return archive


def run(*, hardware=False, confirmation=None):
    global _USED
    if hardware is not True or confirmation != 'RUN-CONTINUOUS25':
        raise ValueError('requires explicit hardware=True and RUN-CONTINUOUS25')
    if _USED or _PREPARED is None:
        raise RuntimeError('prepare once in the second cell; no repeat attempts')
    if __package__:
        from .continuous_guard import verify_package
        from .lean_ps_guard import verify_source, sha
        from .run_lean_ps import require_short, lean_identity
        from .browser_heart_display import install_browser_display
        from .continuous_runtime import start_owner
        from .run_startup180 import load_display
    else:
        from continuous_guard import verify_package
        from lean_ps_guard import verify_source, sha
        from run_lean_ps import require_short, lean_identity
        from browser_heart_display import install_browser_display
        from continuous_runtime import start_owner
        from run_startup180 import load_display
    checked = verify_package(ROOT)
    source = ROOT.parent/'v3b25 native100 heart video'
    prepared = verify_source(ROOT, source, hardware=True)
    require_short(ROOT, prepared)
    bridge, control = _PREPARED['bridge'].require_ready(), _PREPARED['control']
    if prepared != _PREPARED['prepared'] or checked != _PREPARED['checked']:
        raise ValueError('prepared continuous identity changed')
    directory = ROOT/'continuous-results'
    if directory.exists() or (ROOT/'continuous-attempt.json').exists():
        raise FileExistsError('existing continuous attempt; preserve, no retry')
    _USED = True
    write_new(ROOT/'continuous-attempt.json', dict(checked=checked, prepared=prepared,
        token=control.token, automatic_retry=False, duration_mode='manual_until_stop_v1'))
    directory.mkdir(exist_ok=False)
    report = dict(error=None, owner_exitcode=None)
    renderer = None
    try:
        with install_browser_display(ROOT, bridge):
            display = load_display(ROOT)
            if display.hardware_imported():
                raise RuntimeError('display kernel already imported hardware; use a fresh Notebook')
            identity, cached = display.bootstrap(ROOT/'frozen/base', algorithm=False)
            display.load_owner(ROOT/'frozen/base').prepare_display(identity)
            from owner25.transport import Mailbox
            from v3a_25hz_live.view import LiveView25
            context = mp.get_context('spawn')
            mailbox, stop, manual, metrics_ready = Mailbox(context), context.Event(), context.Event(), context.Event()
            renderer = streaming_renderer(bridge, directory)
            view = LiveView25(lambda:mailbox.snapshot(), renderer)
            def start():
                return start_owner(context, ROOT/'frozen/base', directory, mailbox, stop, metrics_ready,
                    root=ROOT, source=source, manual=manual, manifest_sha=sha(ROOT/'continuous-manifest.json'))
            print('持续采集：25/25Hz＋5fps；原保护不变。请保持本单元和页面打开，用正常停止按钮结束。', flush=True)
            report = drive_owner(start, mailbox, control, stop, manual, metrics_ready, view, directory,
                                 renderer_metrics=renderer.metrics)
    except (Exception, KeyboardInterrupt) as exc:
        report['error'] = report['error'] or describe(exc, 'parent_setup')
    finally:
        if renderer is not None:
            renderer.sink.close()
    def read(name):
        path = directory/name
        return json.loads(path.read_text('utf-8')) if path.is_file() else {}
    inherited, owner = read('owner_result.json'), read('concurrent_owner_result.json')
    summary = inherited.get('summary') or {}
    error = report['error'] or inherited.get('error')
    identity_error = None
    try:
        if verify_package(ROOT) != checked or verify_source(ROOT, source, hardware=True) != prepared:
            raise ValueError('continuous package/source changed during capture')
    except Exception as exc:
        identity_error = describe(exc, 'postrun_identity')
    result = assess_manual(summary, owner, parent_error=error or identity_error,
                           requested=control.accepted_ns is not None, owner_exitcode=report.get('owner_exitcode'))
    result['checks']['lean_ps_import_scope'] = lean_identity(summary.get('isolation') or {}, prepared)
    result['artifact_audit'] = audit_artifacts(directory, summary, owner)
    result['checks'].update(result['artifact_audit']['checks'])
    result['manual_session_passed'] = all(result['checks'].values())
    result.update(parent=report, original_error=inherited.get('error'), identity_error=identity_error,
        stop_request=control.request, stop_accepted_ns=control.accepted_ns,
        prepared=prepared, raw_hz=25, processing_hz=25, video_target_fps=5,
        elapsed_seconds=summary.get('elapsed_seconds'), bridge=bridge.report(),
        scope='Manual continuous pilot; no old60, accuracy, strict realtime or full V3B relabelling')
    if report.get('cancelled_before_owner'):
        result.update(hardware_never_started=True, cancelled_before_owner=True, resources_released=True)
    archive = export_result(ROOT, result, control)
    bridge.close()
    print('已导出：'+str(archive)+'；持续会话基础检查：'+str(result['manual_session_passed']), flush=True)
    from IPython.display import display as show, FileLink
    show(FileLink(archive.name))
    return result
