"""One static run, no retries; stop waits for the original ownership cleanup."""
import json
from pathlib import Path
import platform
import sys
import time
from .delivery import FLAGS, digest, new_output, validate


def _error(exc,stage):
    return dict(stage=stage,type=type(exc).__name__,message=str(exc))


def execute(session):
    error = None
    try:
        session.start()
        print('预热完成，进入60秒正式静止采集；不绘图。',flush=True)
        while session.snapshot().state == 'running': time.sleep(.1)
    except (Exception,KeyboardInterrupt) as exc:
        error = _error(exc,'session')
    finally:
        while True:
            try:
                summary = session.stop()
                if summary['cleanup_complete']: break
                print('清理尚未完成，保留所有权继续等待；不要启动其他硬件程序。',flush=True)
                time.sleep(.1)
            except KeyboardInterrupt as exc:
                error = error or _error(exc,'cleanup')
    return summary,error


def run(root, output=None, *, hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    root = Path(root).resolve()
    validate(root)
    directory = new_output(root,output)
    report = dict(schema='v3a25_static_run_v1',**FLAGS,static_pilot_completed=False,
        pilot25_manifest_sha256=digest(root/'pilot25-manifest.json'),python=sys.version,machine=platform.machine(),
        raw_hz=50,processing_hz=25,duration_seconds=60.,error=None,summary=None,backend_fault='',
        capture_directory=str(directory/'capture'))
    session = None
    print('请放稳手指，只运行这一次静止采集；将加载原Overlay，DDR仍未验收。',flush=True)
    print('独立PS进程预热另计，最长60秒；正式采集60秒。',flush=True)
    try:
        from .board import prepare
        session = prepare(root,directory/'capture',hardware=True)
        summary,error = execute(session)
        report.update(summary=summary,error=error,
            static_pilot_completed=bool(summary.get('static_pilot_completed') and error is None),
            backend_fault=getattr(session.backend,'_fault',''))
    except (Exception,KeyboardInterrupt) as exc:
        report['error'] = _error(exc,'preflight' if session is None else 'execution')
        if session is not None:
            report['backend_fault'] = getattr(session.backend,'_fault','')
    with (directory/'run25.json').open('x',encoding='utf8') as stream:
        json.dump(report,stream,ensure_ascii=False,allow_nan=False,indent=2)
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
    print('结果目录：'+str(directory),flush=True)
    return report
