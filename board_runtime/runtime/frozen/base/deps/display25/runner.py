"""One Notebook cell owns display lifecycle; frozen session owns hardware."""
import json
from pathlib import Path
import platform
import sys
import time
from .delivery import FLAGS, digest, new_output, validate, verify_imports


def require_notebook():
    try:
        from IPython import get_ipython
    except ImportError as exc:
        raise RuntimeError('需要板端Notebook的IPython环境；不在此处安装依赖') from exc
    shell = get_ipython()
    if shell is None or getattr(shell,'kernel',None) is None:
        raise RuntimeError('必须在板端Notebook代码单元运行，不能用终端或subprocess启动显示')


def _error(exc,stage):
    return dict(stage=stage,type=type(exc).__name__,message=str(exc))


def _stop(session,metrics=None):
    error = None
    while True:
        try:
            summary = session.stop(display_metrics=metrics)
            if summary['cleanup_complete']: return summary,error
            print('清理未完成，保留原会话所有权继续等待；不要运行其他采集。',flush=True)
            time.sleep(.1)
        except KeyboardInterrupt as exc:
            error = error or _error(exc,'cleanup')
            if metrics is not None: metrics['loop_error'] = metrics.get('loop_error') or error


def execute(session,view,renderer):
    error = None
    try:
        session.start()
        print('预热完成：60秒静止采集与显示已同时运行，请保持本页打开。',flush=True)
        while session.snapshot().state == 'running':
            view.refresh()
            if view.metrics()['display_errors']:
                raise RuntimeError('显示发送失败：'+view.metrics()['error'])
            time.sleep(.02)
    except (Exception,KeyboardInterrupt) as exc:
        error = _error(exc,'session_or_display')
    finally:
        clear = False
        try:
            clear = view.finish()
            if not clear:
                error = error or _error(RuntimeError(view.metrics()['error'] or '终止清屏失败'),'display_finish')
        except (Exception,KeyboardInterrupt) as exc:
            error = error or _error(exc,'display_finish')
        metrics = dict(view.metrics(),**renderer.metrics(),final_clear_published=clear,
                       loop_error=error,measurement_scope='kernel_publish')
        summary,cleanup_error = _stop(session,metrics)
        error = error or cleanup_error
    return summary,error


def run(root,output=None,*,hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    require_notebook()
    root = Path(root).resolve()
    validate(root)
    verify_imports(root)
    directory = new_output(root,output)
    report = dict(schema='v3a25_display_run_v1',**FLAGS,display_pilot_completed=False,
        display25_manifest_sha256=digest(root/'display25-manifest.json'),
        python=sys.version,machine=platform.machine(),raw_hz=50,processing_hz=25,duration_seconds=60.,
        error=None,summary=None,backend_fault='',capture_directory=str(directory/'capture'),
        browser_display_measured=False,display_measurement_scope='kernel_publish')
    session = renderer = None
    execute_entered = False
    print('请放稳手指，只运行本单元；将加载原Overlay，DDR仍未验收。',flush=True)
    print('预热最长60秒另计；正式采集与显示60秒。不要同时采集或绘图。',flush=True)
    try:
        from heart_v3a.live.contracts import LiveSnapshot
        from v3a_25hz_live.view import LiveView25, presentation25
        from pilot25.board import prepare
        from .render import NotebookRenderer, ipython_publisher
        from .assessment import assess
        renderer = NotebookRenderer(ipython_publisher())
        initial = LiveSnapshot('preflight',None,None,(),{})
        value = presentation25(initial,time.monotonic_ns())
        value['reason_cn'] = '正在预热／等待正式采集；此时不显示心率'
        renderer(initial,value)
        session = prepare(root/'static',directory/'capture',hardware=True)
        session._assess_summary = assess
        session._preflight['display25_manifest_sha256'] = report['display25_manifest_sha256']
        view = LiveView25(session.snapshot,renderer)
        execute_entered = True
        summary,error = execute(session,view,renderer)
        report.update(summary=summary,error=error,
            display_pilot_completed=bool(summary.get('display_pilot_completed') and error is None),
            backend_fault=getattr(session.backend,'_fault',''))
    except (Exception,KeyboardInterrupt) as exc:
        report['error'] = _error(exc,'execution' if execute_entered else 'preflight')
        if session is not None:
            report['backend_fault'] = getattr(session.backend,'_fault','')
            if not execute_entered:
                try:
                    report['preflight_cleanup'],report['cleanup_error'] = _stop(session)
                except Exception as cleanup_exc:
                    report['cleanup_error'] = _error(cleanup_exc,'cleanup')
        report['display_attempts'] = renderer.metrics() if renderer is not None else None
    with (directory/'run_display25.json').open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print('本次结束。结果目录：'+str(directory),flush=True)
    print('并发显示基础检查：'+str(report['display_pilot_completed'])+'；不代表完整实时／准确率／DDR通过。',flush=True)
    if report['error']: print('错误已保存，请回传报告；不要自动重试。'+str(report['error']),flush=True)
    from IPython.display import FileLink,display
    for path in (directory/'run_display25.json',*(directory/'capture'/name for name in ('raw.csv','results.csv','events.jsonl','summary.json'))):
        if path.is_file():
            try: display(FileLink(str(path.relative_to(Path.cwd()))))
            except ValueError: print(str(path),flush=True)
    return report
