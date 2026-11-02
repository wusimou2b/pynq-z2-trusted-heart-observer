"""Independent candidate static pilot. CLI only checks; Notebook must opt into hardware."""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
from entry25_guard import (FLAGS, MANIFEST, VARIANT, validate, activate, identity,
                           changed, write_new)

ROOT = Path(__file__).resolve().parent


def describe(exc):
    return dict(type=type(exc).__name__, message=str(exc))


def entry_owner(base, directory, mailbox, stop, metrics_ready):
    original_bootstrap = original_worker = identity_module = bridge = None
    tracked = {}
    failure = None
    try:
        tracked = validate(ROOT)
        activate(ROOT)
        from effective25 import identity as identity_module
        import run_effective25_gc_window as control
        original_bootstrap = identity_module.bootstrap
        def bootstrap(*args, **kwargs):
            nonlocal bridge, original_worker
            result = original_bootstrap(*args, **kwargs)
            if kwargs.get('algorithm') and bridge is None:
                from effective25 import bridge as loaded_bridge
                from entry25_worker import worker
                bridge = loaded_bridge
                original_worker = bridge.worker
                bridge.worker = worker
            return result
        identity_module.bootstrap = bootstrap
        # Original GC observer begins before bootstrap; its window and all cleanup stay original.
        control.window_owner(base, directory, mailbox, stop, metrics_ready)
    except BaseException as exc:
        failure = describe(exc)
        raise
    finally:
        if original_bootstrap is not None:
            identity_module.bootstrap = original_bootstrap
        if original_worker is not None:
            bridge.worker = original_worker
        write_new(Path(directory)/'owner_entry25.json', dict(schema='entry25_owner_v1',
            **identity(ROOT), owner_pid=os.getpid(), parent_pid=os.getppid(),
            worker_binding_installed=original_worker is not None, wrapper_error=failure,
            entry_files_unchanged=bool(tracked) and not changed(ROOT, tracked)))


def _start_entry_owner(context, base, directory, mailbox, stop, metrics_ready):
    process = context.Process(target=entry_owner,
        args=(base, directory, mailbox, stop, metrics_ready), name='entry25-six-check-owner', daemon=False)
    process.start()
    return process


def run_static60(*, hardware=False, output=None):
    if hardware is not True:
        raise ValueError('必须显式hardware=True；本入口会加载原Overlay并进行一次60秒静止采集')
    tracked = validate(ROOT)
    activate(ROOT)
    import run_effective25_gc_window as control
    directory = Path(output).resolve() if output else ROOT/'live_results'/('entry6-static-'+uuid.uuid4().hex[:12])
    if directory.exists():
        raise FileExistsError('结果目录已存在，禁止覆盖：'+str(directory))
    if not directory.is_relative_to(ROOT/'live_results') or directory == ROOT/'live_results':
        raise ValueError('候选结果只允许保存在entry25_live/live_results的新子目录')
    print('本次是6次进入确认候选，不是旧版2次：先只做一次60秒静止测试。', flush=True)
    print('放稳手指，关闭其他采集；将加载原Overlay，DDR仍未验收。不要运行旧采集单元。', flush=True)
    print('25/25、原退出/质量/两个新间隔保护和所有者GC窗口不变；运动测试暂不启动。', flush=True)
    original_start = control._start_window_owner
    window, failure = {}, None
    control._start_window_owner = _start_entry_owner
    try:
        window = control.run_gc_window60(hardware=True, output=directory)
    except BaseException as exc:
        failure = describe(exc)
        # The frozen run owns its cleanup/finally. Never attempt a second capture here.
        if not directory.is_dir():
            raise
    finally:
        control._start_window_owner = original_start
    from entry25_report import save
    report, archive = save(ROOT, directory, window, tracked, failure)
    print('候选静止基础小试完成：'+str(report['candidate_static_pilot_completed']), flush=True)
    print(report['caveat_cn'], flush=True)
    print('请回传这个结果ZIP；不要自动重试或进入运动测试：'+str(archive), flush=True)
    from IPython.display import FileLink, display
    try:
        display(FileLink(str(archive.relative_to(Path.cwd()))))
    except ValueError:
        print(str(archive), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle', action='store_true')
    parser.parse_args()
    validate(ROOT)
    print(json.dumps(dict(bundle_validated=True, variant=VARIANT,
        raw_hz=25, processing_hz=25, entry_confirmation_checks=6, duration_seconds=60,
        hardware_loaded=False, candidate_static_pilot_completed=False, **FLAGS)))


if __name__ == '__main__':
    main()
