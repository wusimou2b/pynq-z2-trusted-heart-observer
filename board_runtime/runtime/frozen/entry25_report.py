"""Post-cleanup candidate identity and inherited pilot checks; not formal acceptance."""
from pathlib import Path
import zipfile

from entry25_guard import VARIANT, CANDIDATE_SHA, FLAGS, sha, document, write_new, changed


def assemble(run, window, owner, changed_files, manifest_sha, wrapper_error=None):
    summary = run.get('summary') or {}
    worker = summary.get('isolation') or {}
    owner = owner or {}
    expected = dict(entry_variant=VARIANT, entry_confirmation_checks=6,
                    entry_candidate_sha256=CANDIDATE_SHA, entry_manifest_sha256=manifest_sha)
    count = summary.get('read', 0)
    checks = dict(
        inherited_display=run.get('display_pilot_completed') is True
            and run.get('owner_display_pilot_completed') is True,
        inherited_gc=window.get('control_pilot_completed') is True
            and window.get('comparison_valid') is True and window.get('physical_memory_measured') is True,
        full_duration=summary.get('elapsed_seconds', 0) >= 60.
            and summary.get('stop_reason') == 'duration_complete' and summary.get('state') == 'stopped',
        no_fault=bool(summary) and summary.get('fault') is None and run.get('error') is None
            and wrapper_error is None and bool(owner) and owner.get('wrapper_error') is None,
        real_backend=summary.get('backend_source') == 'pl_mmio',
        rates=(summary.get('raw_hz'), summary.get('processing_hz')) == (25,25),
        counts=count > 0 and all(summary.get(key) == count for key in ('raw_saved','processed','results_saved'))
            and worker.get('completed_steps') == count and worker.get('pl_requests') == count,
        queues=summary.get('queue_full') == dict(raw=0, processing=0, results=0),
        candidate_worker=all(worker.get(key) == value for key, value in expected.items()),
        candidate_owner=all(owner.get(key) == value for key, value in expected.items()),
        three_processes=all(type(pid) is int and pid > 0 for pid in
            (run.get('parent_pid'), run.get('owner_pid'), worker.get('worker_pid')))
            and len({run.get('parent_pid'), run.get('owner_pid'), worker.get('worker_pid')}) == 3
            and owner.get('owner_pid') == run.get('owner_pid')
            and owner.get('parent_pid') == run.get('parent_pid')
            and worker.get('parent_pid') == run.get('owner_pid'),
        isolation=run.get('parent_hardware_imported') is False
            and run.get('parent_algorithm_imported') is False
            and worker.get('worker_hardware_imported') is False,
        cleanup=run.get('cleanup_complete') is True and summary.get('cleanup_complete') is True
            and run.get('owner_exitcode') == 0 and worker.get('exitcode') == 0
            and worker.get('cleanup_complete') is True and worker.get('forced_termination') is False
            and worker.get('fault') == '',
        unchanged=not changed_files and run.get('inputs_unchanged') is True
            and window.get('inputs_unchanged') is True and owner.get('entry_files_unchanged') is True,
        formal_flags_false=all(run.get(key) is False and summary.get(key) is False for key in FLAGS))
    return dict(schema='entry25_static_pilot_v1', variant=VARIANT,
        candidate_static_pilot_completed=all(checks.values()), checks=checks, **FLAGS,
        accuracy_validated=False, realtime_validated=False, entry_confirmation_checks=6,
        entry_candidate_sha256=CANDIDATE_SHA, entry_manifest_sha256=manifest_sha,
        raw_hz=25, processing_hz=25, protocol='static', requested_duration_seconds=60.,
        summary=run.get('summary'), capture_error=run.get('error'), wrapper_error=wrapper_error,
        owner_entry=owner, changed_files=list(changed_files),
        caveat_cn='只验证本次6次确认候选静止小试；不是运动改善、准确率、DDR或完整V3a验收。'
        '基础GC报告描述原组件，其“算法不变”不表示本候选未改进入确认。'
        '退出/接触/质量/两个新间隔保护、位流、25/25和GC窗口不变。原模板50Hz脚注未改；有效原始为25Hz。')


def archive_results(directory):
    directory = Path(directory)
    archive = directory/'entry25_results.zip'
    names = ('run_entry25_live.json', 'run_entry25_live.txt', 'owner_entry25.json',
             'gc_window.json', 'gc_window.txt', 'owner_gc_window.json', 'owner_gc.json',
             'run_effective25_display.json', 'owner_result.json', 'display_metrics.json',
             'capture/raw.csv', 'capture/results.csv', 'capture/events.jsonl', 'capture/summary.json')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as stream:
        for name in names:
            if (directory/name).is_file():
                stream.write(directory/name, name)
    return archive


def save(root, directory, window, tracked, wrapper_error=None):
    directory = Path(directory)
    def read(name):
        return document(directory/name) if (directory/name).is_file() else {}
    report = assemble(read('run_effective25_display.json'), window, read('owner_entry25.json'),
                      changed(root, tracked), tracked['entry25-live-manifest.json'], wrapper_error)
    report['input_sha256'] = {p.relative_to(directory).as_posix(): sha(p)
        for p in sorted(directory.rglob('*')) if p.is_file()}
    write_new(directory/'run_entry25_live.json', report)
    lines = ['6次进入确认：独立25/25静止实采候选',
        '候选静止基础小试完成：'+str(report['candidate_static_pilot_completed']),
        '未通过项：'+str([key for key, value in report['checks'].items() if not value]),
        '采集错误：'+str(report['capture_error']), '入口错误：'+str(report['wrapper_error']),
        report['caveat_cn'], '请回传entry25_results.zip；不自动重试，不自动进入运动测试。']
    with (directory/'run_entry25_live.txt').open('x', encoding='utf8') as stream:
        stream.write('\n'.join(lines)+'\n')
    return report, archive_results(directory)
