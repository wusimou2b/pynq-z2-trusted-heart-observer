"""Owner-only GC observation. No algorithm, timing gate or GC-policy changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

from effective25_gc_log import GCLog

ROOT = Path(__file__).resolve().parent
BASE_SHA = '400883a9049ad8684fbc15102032cfe8dc0a1daaabda8110423f31959ec054b1'
ADDON_FILES = ('run_effective25_gc_probe.py', 'effective25_gc_log.py',
               'effective25_gc_report.py', 'README_GC_PROBE.md')
FLAGS = dict.fromkeys(('live_25hz_passed', 'live_50hz_passed', 'auto_beta_effect_passed',
    'board_ddr_verified', 'limits_frozen', 'run_acceptance_passed', 'v3a_complete'), False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def describe(exc):
    return dict(type=type(exc).__name__, message=str(exc))


def validate_base(root):
    root = Path(root).resolve()
    path = root/'effective25-manifest.json'
    if not path.is_file() or sha(path) != BASE_SHA:
        raise ValueError('effective25基础包身份不符；请使用25/25目录')
    existing = sys.modules.get('effective25')
    if existing and not Path(existing.__file__).resolve().is_relative_to(root):
        raise ValueError('内核串包，请新建Notebook')
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from effective25.identity import validate
    return validate(root)


def validate_addon(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'gc-probe-manifest.json').read_text(encoding='utf8'))
    if (manifest.get('schema') != 'effective25_gc_addon_v1'
            or manifest.get('base_manifest_sha256') != BASE_SHA
            or set(manifest.get('files', {})) != set(ADDON_FILES)):
        raise ValueError('GC观测附加包清单身份不符')
    tracked = {'gc-probe-manifest.json': sha(root/'gc-probe-manifest.json')}
    for name, expected in manifest['files'].items():
        if not (root/name).is_file() or sha(root/name) != expected:
            raise ValueError('GC观测文件身份不符：'+name)
        tracked[name] = expected
    return tracked


def gc_owner(root, directory, mailbox, stop, metrics_ready):
    # Fresh spawn, original owner main does all preparation/start/stop/cleanup.
    from effective25.owner import main as original_main
    log = GCLog()
    failure = None
    try:
        log.start()
        original_main(root, directory, mailbox, stop, metrics_ready)
    except BaseException as exc:
        failure = describe(exc)
        raise
    finally:
        log.stop()
        path = Path(directory)/'owner_result.json'
        owner = json.loads(path.read_text(encoding='utf8')) if path.is_file() else {}
        write_new(Path(directory)/'owner_gc.json', dict(schema='effective25_owner_gc_v1',
            owner_pid=os.getpid(), parent_pid=os.getppid(), wrapper_error=failure,
            capture_cleanup_complete=owner.get('cleanup_complete', False), gc=log.report(),
            base_manifest_sha256=BASE_SHA,
            source_sha256={name: sha(ROOT/name) for name in
                          ('run_effective25_gc_probe.py', 'effective25_gc_log.py')}))


def _start_gc_owner(context, root, directory, mailbox, stop, metrics_ready):
    process = context.Process(target=gc_owner,
        args=(root, directory, mailbox, stop, metrics_ready),
        name='effective25-gc-owner', daemon=False)
    process.start()
    return process


def run_gc_probe60(*, hardware=False, output=None):
    if hardware is not True:
        raise ValueError('必须显式hardware=True')
    tracked = validate_addon(ROOT)
    validate_base(ROOT)
    from effective25 import display as entry
    directory = Path(output).resolve() if output else ROOT/'live_results'/('gc-effective25-'+uuid.uuid4().hex[:12])
    print('最小GC观测：只观察所有者；请放稳手指，只运行本次采集。', flush=True)
    print('25/25与原保护不变；不禁用、不强制GC；原收尾完成后才导出。', flush=True)
    original_start = entry._start_owner
    entry._start_owner = _start_gc_owner
    try:
        run = entry.run(ROOT, directory, hardware=True)
    finally:
        entry._start_owner = original_start
    # No report/CSV analysis while the original capture or cleanup is active.
    from effective25_gc_report import assemble, report_text
    changed = [name for name, expected in tracked.items()
               if not (ROOT/name).is_file() or sha(ROOT/name) != expected]
    changed += run.get('changed_files', [])
    owner_path = directory/'owner_gc.json'
    owner = json.loads(owner_path.read_text(encoding='utf8')) if owner_path.is_file() else None
    if owner and (owner.get('base_manifest_sha256') != BASE_SHA
            or any(owner.get('source_sha256', {}).get(name) != tracked[name]
                   for name in ('run_effective25_gc_probe.py', 'effective25_gc_log.py'))):
        changed.append('owner_gc_identity')
    report = assemble(directory, run, owner, changed)
    names = ('owner_gc.json', 'run_effective25_display.json', 'owner_result.json',
             'display_metrics.json', 'capture/raw.csv', 'capture/results.csv',
             'capture/events.jsonl', 'capture/summary.json')
    report['input_sha256'] = {name: sha(directory/name) for name in names if (directory/name).is_file()}
    write_new(directory/'gc_probe.json', report)
    text = report_text(report)
    with (directory/'gc_probe.txt').open('x', encoding='utf8') as stream:
        stream.write(text)
    print(text, flush=True)
    from IPython.display import FileLink, display
    for name in ('gc_probe.json', 'gc_probe.txt', 'owner_gc.json', 'display_metrics.json', 'owner_result.json'):
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
    validate_base(ROOT)
    print(json.dumps(dict(bundle_validated=True, diagnostic_only=True, observed_process='owner_only',
        raw_hz=25, processing_hz=25, gc_policy_changed=False, hardware_loaded=False, **FLAGS)))


if __name__ == '__main__':
    main()
