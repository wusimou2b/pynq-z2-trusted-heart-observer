"""25/25 entry, preserving the frozen three-process display lifecycle."""
import multiprocessing as mp
import json
import os
from pathlib import Path
import sys
import time
import uuid
from .identity import bootstrap, load_owner, write_new, FLAGS


def error(exc,stage): return dict(stage=stage,type=type(exc).__name__,message=str(exc))


def hardware_imported():
    return any(n=='pynq' or n.startswith('pynq.') for n in sys.modules)


def algorithm_imported():
    return any(n.startswith(('heart_v2.','heart_v3a.runtime','v3a_rate25.'))
        or n in ('peak_chain','peak_timing','v3a_25hz_live.session','pilot25.board',
                 'effective25.board','effective25.session','effective25.checks') for n in sys.modules)


def _start_owner(context, root, directory, mailbox, stop, metrics_ready):
    from .owner import main
    process=context.Process(target=main,args=(root,directory,mailbox,stop,metrics_ready),
                            name='effective25-hardware-owner',daemon=False)
    process.start()
    return process


def run(root, output=None, *, hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    try:
        from IPython import get_ipython
    except ImportError as exc:
        raise RuntimeError('需要板端Notebook；不要安装新依赖') from exc
    if getattr(get_ipython(),'kernel',None) is None: raise RuntimeError('请在新Notebook直接调用')
    if hardware_imported(): raise RuntimeError('显示内核已导入pynq，请关闭旧采集并使用新Notebook内核')
    identity,cached = bootstrap(root,algorithm=False)
    candidate = load_owner(root).prepare_display(identity)
    if hardware_imported(): raise RuntimeError('显示进程不得导入pynq')
    root = identity['effective_root']
    from display25.delivery import new_output
    from display25.render import ipython_publisher
    from v3a_25hz_live.view import LiveView25
    from owner25.transport import Mailbox
    directory = new_output(root,output or root/'live_results'/('effective25-display-'+uuid.uuid4().hex[:12]))
    ctx = mp.get_context('spawn')
    mailbox,stop,metrics_ready = Mailbox(ctx),ctx.Event(),ctx.Event()
    process = None
    last_snapshot = mailbox.snapshot()
    report = dict(schema='effective25_owner_display_run_v1',**FLAGS,owner_display_pilot_completed=False,
        display_pilot_completed=False,parent_pid=os.getpid(),owner_pid=None,owner_exitcode=None,
        parent_hardware_imported=False,parent_algorithm_imported=False,
        cleanup_complete=False,summary=None,error=None,owner_result=None,
        adc_hz=50,raw_hz=25,processing_hz=25,fifo_sample_average=2,duration_seconds=60.,protocol='static',mode='baseline',
        effective_manifest_sha256=identity['effective_manifest_sha256'],owner_manifest_sha256=identity['owner_manifest_sha256'],inputs_unchanged=False,changed_files=[],
        browser_display_measured=False,display_measurement_scope='kernel_publish')

    def provider():
        nonlocal last_snapshot
        mailbox.touch()
        last_snapshot = mailbox.snapshot(alive=process is None or process.is_alive())
        return last_snapshot

    renderer = cached.CachedRenderer(ipython_publisher(),candidate.CachedSvgBuilder())
    view = LiveView25(provider,renderer)
    initial_ok = False
    print('三进程静止小试：请放稳手指；有效原始25Hz／处理25Hz，四曲线约2次/秒。',flush=True)
    print('只有独立所有者加载原Overlay；DDR仍未验收。预热另计，正式60秒。',flush=True)
    try:
        if not view.refresh(): raise RuntimeError('初始N/A发送失败：'+view.metrics()['error'])
        initial_ok = True
        process = _start_owner(ctx,root,directory,mailbox,stop,metrics_ready)
        report['owner_pid'] = process.pid
        announced = False
        started = time.monotonic()
        while process.is_alive():
            snap = provider()
            if snap.state == 'running' and not announced:
                print('预热完成：采集与显示已分别运行，请保持本单元和页面打开。',flush=True)
                announced = True
            if snap.state not in ('preflight','running'):
                if snap.fault is not None: raise RuntimeError(snap.fault.reason)
                break
            if not announced and time.monotonic()-started > 90:
                raise TimeoutError('所有者启动超过90秒，请求停止并等待真实清理')
            view.refresh()
            if view.metrics()['display_errors']: raise RuntimeError(view.metrics()['error'])
            time.sleep(.02)
        if not process.is_alive() and process.exitcode != 0:
            raise RuntimeError('硬件所有者异常退出；清理状态未验证，禁止重采')
    except (Exception,KeyboardInterrupt) as exc:
        report['error'] = error(exc,'display_or_owner')
    finally:
        stop.set()
        # Do not require a live child to send the final historical N/A.
        view.provider = lambda:last_snapshot
        clear = False
        if initial_ok:
            try: clear = view.finish()
            except (Exception,KeyboardInterrupt) as exc:
                report['error'] = report['error'] or error(exc,'final_clear')
        metrics = dict(view.metrics(),**renderer.metrics(),final_clear_published=clear,
            loop_error=report['error'],measurement_scope='kernel_publish')
        try: write_new(directory/'display_metrics.json',metrics)
        except Exception as exc:
            report['error'] = report['error'] or error(exc,'write_display_metrics')
        metrics_ready.set()
        if process is not None:
            announced_wait = time.monotonic()
            while process.is_alive():
                try: process.join(.1)
                except KeyboardInterrupt:
                    report['error'] = report['error'] or error(KeyboardInterrupt('等待硬件清理'),'cleanup')
                if time.monotonic()-announced_wait > 5:
                    print('仍在等待所有者清理；不强杀，不启动其他采集。',flush=True)
                    announced_wait = time.monotonic()
            report['owner_exitcode'] = process.exitcode
            if (directory/'owner_result.json').is_file():
                owner = json.loads((directory/'owner_result.json').read_text(encoding='utf8'))
                report.update(owner_result=owner,summary=owner['summary'],
                    cleanup_complete=owner['cleanup_complete'] and process.exitcode == 0)
                report['error'] = report['error'] or owner['error']
            else: report['error'] = report['error'] or error(RuntimeError('缺少所有者收尾报告'),'cleanup')
            process.close()
        report['parent_hardware_imported'] = hardware_imported()
        report['parent_algorithm_imported'] = algorithm_imported()
        report['display_attempts'] = renderer.metrics()
        report['changed_files'] = cached.changed_files(identity)
        report['inputs_unchanged'] = not report['changed_files']
        if report['changed_files']:
            report['error'] = report['error'] or error(ValueError('运行期间文件身份改变'),'integrity')
        if not clear and initial_ok:
            report['error'] = report['error'] or error(RuntimeError('最终N/A未成功发送'),'final_clear')
        passed = bool(report['summary'] and report['summary'].get('display_pilot_completed')
            and report['error'] is None and report['cleanup_complete'] and report['inputs_unchanged']
            and not report['parent_hardware_imported'] and report['owner_pid'] != report['parent_pid'])
        report['owner_display_pilot_completed'] = report['display_pilot_completed'] = passed
        write_new(directory/'run_effective25_display.json',report)
    print('结果目录：'+str(directory),flush=True)
    print('三进程显示基础检查：'+str(passed)+'；不是完整V3a、准确率或DDR验收。',flush=True)
    if report['error']: print('请保留结果，不自动重试。'+str(report['error']),flush=True)
    from IPython.display import FileLink,display
    for path in (directory/'run_effective25_display.json',*(directory/'capture'/name
            for name in ('raw.csv','results.csv','events.jsonl','summary.json'))):
        if path.is_file():
            try: display(FileLink(str(path.relative_to(Path.cwd()))))
            except ValueError: print(str(path),flush=True)
    return report
