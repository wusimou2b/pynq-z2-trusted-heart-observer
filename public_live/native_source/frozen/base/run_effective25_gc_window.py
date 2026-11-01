"""Single owner-only GC-window experiment; frozen 25/25 protection stays active."""
import argparse
import json
import os
from pathlib import Path
import uuid

import run_effective25_gc_probe as probe
from effective25_gc_window import Window, install_session, memory_snapshot

ROOT = Path(__file__).resolve().parent
BASE_SHA = probe.BASE_SHA
PROBE_SHA = '2c6b9098cf713937d84b1ee3c383746ebfd2eb031dc44b9c63ad08345c99e228'
ADDON_FILES = ('run_effective25_gc_window.py', 'effective25_gc_window.py',
               'effective25_gc_window_report.py', 'README_GC_WINDOW.md')
FLAGS = probe.FLAGS


def validate_prerequisite(root):
    root = Path(root).resolve()
    path = root/'gc-probe-manifest.json'
    if not path.is_file() or probe.sha(path) != PROBE_SHA:
        raise ValueError('缺少匹配的最小GC观测包；请使用上次v3a25_all目录，不覆盖旧文件')
    tracked = probe.validate_addon(root)
    probe.validate_base(root)
    return tracked


def validate_addon(root):
    root = Path(root).resolve()
    tracked = validate_prerequisite(root)
    manifest = json.loads((root/'gc-window-manifest.json').read_text(encoding='utf8'))
    if (manifest.get('schema') != 'effective25_gc_window_addon_v1'
            or manifest.get('base_manifest_sha256') != BASE_SHA
            or manifest.get('probe_manifest_sha256') != PROBE_SHA
            or set(manifest.get('files', {})) != set(ADDON_FILES)):
        raise ValueError('GC窗口对照包身份不符')
    tracked['gc-window-manifest.json'] = probe.sha(root/'gc-window-manifest.json')
    for name, expected in manifest['files'].items():
        if not (root/name).is_file() or probe.sha(root/name) != expected:
            raise ValueError('GC窗口文件身份不符：'+name)
        tracked[name] = expected
    return tracked


def window_owner(root, directory, mailbox, stop, metrics_ready):
    from effective25 import identity
    window = Window()
    original_bootstrap = identity.bootstrap
    board = original_prepare = None
    undo = None
    install_error = wrapper_error = None
    def prepare(*args, **kwargs):
        nonlocal undo, install_error
        session = original_prepare(*args, **kwargs)
        try:
            undo = install_session(session, window)
        except BaseException as exc:
            install_error = probe.describe(exc)
            # Return ownership to frozen owner.main so its finally can clean hardware.
            session._fail('gc_window_install', str(exc))
        return session
    def bootstrap(*args, **kwargs):
        nonlocal board, original_prepare
        result = original_bootstrap(*args, **kwargs)
        if kwargs.get('algorithm') and board is None:
            from effective25 import board as loaded_board
            board = loaded_board
            original_prepare = board.prepare
            board.prepare = prepare
        return result
    # Install only after the original bootstrap, inside the original GC observer.
    identity.bootstrap = bootstrap
    try:
        probe.gc_owner(root, directory, mailbox, stop, metrics_ready)
    except BaseException as exc:
        wrapper_error = probe.describe(exc)
        raise
    finally:
        identity.bootstrap = original_bootstrap
        if board is not None:
            board.prepare = original_prepare
        window.restore('owner_finally_fallback')
        if undo is not None:
            undo()
        probe.write_new(Path(directory)/'owner_gc_window.json', dict(
            schema='effective25_owner_gc_window_v1', owner_pid=os.getpid(),
            parent_pid=os.getppid(), window=window.report(), install_error=install_error,
            wrapper_error=wrapper_error, memory_after_cleanup=memory_snapshot(),
            base_manifest_sha256=BASE_SHA, probe_manifest_sha256=PROBE_SHA,
            source_sha256={name: probe.sha(ROOT/name) for name in
                          ('run_effective25_gc_window.py', 'effective25_gc_window.py')}))


def _start_window_owner(context, root, directory, mailbox, stop, metrics_ready):
    process = context.Process(target=window_owner,
        args=(root, directory, mailbox, stop, metrics_ready),
        name='effective25-gc-window-owner', daemon=False)
    process.start()
    return process


def run_gc_window60(*, hardware=False, output=None):
    if hardware is not True:
        raise ValueError('必须显式hardware=True')
    tracked = validate_addon(ROOT)
    from effective25 import display as entry
    directory = Path(output).resolve() if output else ROOT/'live_results'/('gc-window-effective25-'+uuid.uuid4().hex[:12])
    print('单次GC窗口对照：请放稳手指，只运行本次采集，保持页面打开。', flush=True)
    print('有效原始25Hz／处理25Hz；原100ms状态门、1秒结果门、2秒父心跳不变。', flush=True)
    print('只有所有者在预热后暂缓自动循环GC，工作线程退出后恢复；不强制回收、不调阈值。', flush=True)
    print('显示旧脚注仍写原始50Hz，本次保留模板不改；本次有效原始确为25Hz。', flush=True)
    original_start = entry._start_owner
    entry._start_owner = _start_window_owner
    try:
        run = entry.run(ROOT, directory, hardware=True)
    finally:
        entry._start_owner = original_start
    # Only read CSVs/export extra reports after the frozen cleanup has completed.
    from effective25_gc_window_report import assemble, report_text
    changed = [name for name, expected in tracked.items()
               if not (ROOT/name).is_file() or probe.sha(ROOT/name) != expected]
    changed += run.get('changed_files', [])
    records = []
    for filename, source_names, manifest_key, expected_manifest in (
        ('owner_gc.json', ('run_effective25_gc_probe.py', 'effective25_gc_log.py'),
         'base_manifest_sha256', BASE_SHA),
        ('owner_gc_window.json', ('run_effective25_gc_window.py', 'effective25_gc_window.py'),
         'probe_manifest_sha256', PROBE_SHA)):
        path = directory/filename
        record = json.loads(path.read_text(encoding='utf8')) if path.is_file() else None
        if record and (record.get(manifest_key) != expected_manifest
                or record.get('base_manifest_sha256') != BASE_SHA
                or any(record.get('source_sha256', {}).get(name) != tracked[name] for name in source_names)):
            changed.append(filename+':identity')
        records.append(record)
    report = assemble(directory, run, *records, changed)
    names = ('owner_gc_window.json', 'owner_gc.json', 'run_effective25_display.json',
             'owner_result.json', 'display_metrics.json', 'capture/raw.csv',
             'capture/results.csv', 'capture/events.jsonl', 'capture/summary.json')
    report['input_sha256'] = {name: probe.sha(directory/name) for name in names if (directory/name).is_file()}
    probe.write_new(directory/'gc_window.json', report)
    text = report_text(report)
    with (directory/'gc_window.txt').open('x', encoding='utf8') as stream:
        stream.write(text)
    print(text, flush=True)
    from IPython.display import FileLink, display
    for name in ('gc_window.json', 'gc_window.txt', 'owner_gc_window.json', 'owner_gc.json',
                 'display_metrics.json', 'owner_result.json'):
        target = directory/name
        if target.is_file():
            try:
                display(FileLink(str(target.relative_to(Path.cwd()))))
            except ValueError:
                print(str(target), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle', action='store_true')
    parser.parse_args()
    validate_addon(ROOT)
    print(json.dumps(dict(bundle_validated=True, controlled_experiment=True,
        raw_hz=25, processing_hz=25, gc_window_executed=False,
        hardware_loaded=False, **FLAGS)))


if __name__ == '__main__':
    main()
