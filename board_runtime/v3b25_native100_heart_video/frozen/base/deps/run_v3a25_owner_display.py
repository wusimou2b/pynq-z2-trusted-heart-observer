"""独立硬件所有者＋缓存显示。默认只验包，Notebook显式授权后才启动。"""
import argparse
import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
MANIFEST = 'owner-display25-manifest.json'
CACHED_ENTRY_SHA = '78e3f292dc4815aaa578494ca97920e1516a3550df12b21ff51e164ee8ff00ee'
CACHED_MANIFEST_SHA = 'e99fd0df085b4cf072a8f6a17db32c7fdb163f90c395851d10655ccabc8b21e0'
FILES = {'run_v3a25_owner_display.py','owner25/__init__.py','owner25/transport.py','owner25/worker.py'}
FLAGS = dict.fromkeys(('live_25hz_passed','live_50hz_passed','auto_beta_effect_passed',
    'board_ddr_verified','limits_frozen','run_acceptance_passed','v3a_complete'),False)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def error(exc,stage): return dict(stage=stage,type=type(exc).__name__,message=str(exc))


def validate(root):
    root = Path(root).resolve()
    for name,digest in (('run_v3a25_cached_live.py',CACHED_ENTRY_SHA),
                        ('cached-live25-manifest.json',CACHED_MANIFEST_SHA)):
        if not (root/name).is_file() or sha(root/name) != digest:
            raise ValueError('旧缓存入口身份不符：'+name)
    spec = importlib.util.spec_from_file_location('_owner_cached_entry',root/'run_v3a25_cached_live.py')
    cached = importlib.util.module_from_spec(spec); spec.loader.exec_module(cached)
    context = cached.validate(root)
    document = json.loads((root/MANIFEST).read_text(encoding='utf8'))
    if (document.get('schema') != 'v3a25_owner_display_addon_v1'
            or any(document.get(k) is not False for k in FLAGS)
            or set(document.get('files',{})) != FILES
            or (document.get('raw_hz'),document.get('processing_hz'),document.get('duration_seconds')) != (50,25,60)
            or document.get('cached_manifest_sha256') != CACHED_MANIFEST_SHA):
        raise ValueError('所有者附加包范围／身份不符')
    for name,digest in document['files'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha(path) != digest:
            raise ValueError('所有者文件缺失／改变：'+name)
        context['tracked_hashes'][str(path)] = digest
    for name,module in tuple(sys.modules.items()):
        if name.split('.')[0] == 'owner25':
            file = getattr(module,'__file__',None)
            if file and not Path(file).resolve().is_relative_to(root):
                raise ValueError('旧内核串入owner25，请新建Notebook内核')
    context['owner_manifest_sha256'] = sha(root/MANIFEST)
    context['tracked_hashes'][str(root/MANIFEST)] = context['owner_manifest_sha256']
    return context,cached


def _start_owner(context, root, directory, mailbox, stop, metrics_ready):
    from owner25.worker import main
    process = context.Process(target=main,args=(root,directory,mailbox,stop,metrics_ready),
                              name='v3a25-hardware-owner',daemon=False)
    process.start()
    return process


def hardware_imported():
    return any(n == 'pynq' or n.startswith('pynq.') for n in sys.modules)


def algorithm_imported():
    return any(n.startswith(('heart_v2.','heart_v3a.runtime','v3a_rate25.'))
        or n in ('peak_chain','peak_timing','v3a_25hz_live.session','pilot25.board') for n in sys.modules)


def prepare_display(identity):
    """Load the frozen stdlib-only view/renderer, not the algorithm/session stack."""
    root = identity['root']
    prefixes = ('display25','pilot25','heart_v2','heart_v3a','v3a_25hz_live',
                'v3a_rate25','rate25_tools','owner25')
    for name,module in tuple(sys.modules.items()):
        if name.split('.')[0] in prefixes or name in ('peak_chain','peak_timing','v3a25_cached_display'):
            path = getattr(module,'__file__',None)
            if path and not Path(path).resolve().is_relative_to(root):
                raise ValueError('旧内核串包，请新建Notebook：'+name)
    for path in reversed((root,root/'static',root/'static/checked',root/'static/checked/base')):
        sys.path.insert(0,str(path))
    from display25.delivery import validate as validate_display
    validate_display(root)
    from v3a_25hz_live.view import LiveView25
    from display25.render import ipython_publisher
    spec = importlib.util.spec_from_file_location('_owner_svg',root/'v3a25_cached_display.py')
    candidate = importlib.util.module_from_spec(spec); spec.loader.exec_module(candidate)
    return candidate


def run(root, output=None, *, hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    try:
        from IPython import get_ipython
    except ImportError as exc:
        raise RuntimeError('需要板端Notebook；不要安装新依赖') from exc
    if getattr(get_ipython(),'kernel',None) is None: raise RuntimeError('请在新Notebook直接调用')
    if hardware_imported(): raise RuntimeError('显示内核已导入pynq，请关闭旧采集并使用新Notebook内核')
    identity,cached = validate(root)
    candidate = prepare_display(identity)
    if hardware_imported(): raise RuntimeError('显示进程不得导入pynq')
    root = identity['root']
    from display25.delivery import new_output
    from display25.render import ipython_publisher
    from v3a_25hz_live.view import LiveView25
    from owner25.transport import Mailbox
    directory = new_output(root,output or root/'live_results'/('owner-display25-'+uuid.uuid4().hex[:12]))
    ctx = mp.get_context('spawn')
    mailbox,stop,metrics_ready = Mailbox(ctx),ctx.Event(),ctx.Event()
    process = None
    last_snapshot = mailbox.snapshot()
    report = dict(schema='v3a25_owner_display_run_v1',**FLAGS,owner_display_pilot_completed=False,
        display_pilot_completed=False,parent_pid=os.getpid(),owner_pid=None,owner_exitcode=None,
        parent_hardware_imported=False,parent_algorithm_imported=False,
        cleanup_complete=False,summary=None,error=None,owner_result=None,
        raw_hz=50,processing_hz=25,duration_seconds=60.,protocol='static',mode='baseline',
        owner_manifest_sha256=identity['owner_manifest_sha256'],inputs_unchanged=False,changed_files=[],
        browser_display_measured=False,display_measurement_scope='kernel_publish')

    def provider():
        nonlocal last_snapshot
        mailbox.touch()
        last_snapshot = mailbox.snapshot(alive=process is None or process.is_alive())
        return last_snapshot

    renderer = cached.CachedRenderer(ipython_publisher(),candidate.CachedSvgBuilder())
    view = LiveView25(provider,renderer)
    initial_ok = False
    print('三进程静止小试：请放稳手指；原始50Hz／处理25Hz，四曲线约2次/秒。',flush=True)
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
        write_new(directory/'run_owner_display25.json',report)
    print('结果目录：'+str(directory),flush=True)
    print('三进程显示基础检查：'+str(passed)+'；不是完整V3a、准确率或DDR验收。',flush=True)
    if report['error']: print('请保留结果，不自动重试。'+str(report['error']),flush=True)
    from IPython.display import FileLink,display
    for path in (directory/'run_owner_display25.json',*(directory/'capture'/name
            for name in ('raw.csv','results.csv','events.jsonl','summary.json'))):
        if path.is_file():
            try: display(FileLink(str(path.relative_to(Path.cwd()))))
            except ValueError: print(str(path),flush=True)
    return report


def run_owner_display60(*,hardware=False,output=None):
    return run(ROOT,output,hardware=hardware)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle',action='store_true'); parser.parse_args()
    validate(ROOT)
    print(json.dumps(dict(bundle_validated=True,**FLAGS,hardware_loaded=False,
        raw_hz=50,processing_hz=25,entry='notebook_owner_display60')))


if __name__ == '__main__': main()
