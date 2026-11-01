"""Post-cleanup evidence for one GC intervention; never formal acceptance."""
from effective25_gc_report import assemble as observe, intervals, overlaps


def assemble(directory, run, owner, record, changed):
    report = observe(directory, run, owner, changed)
    record = record or {}
    window = record.get('window') or {}
    capture = report['capture_window']
    start, end = window.get('started_ns', 0), window.get('ended_ns', 0)
    collections, _ = intervals(((owner or {}).get('gc') or {}).get('events', []))
    inside = overlaps(dict(start_ns=start, end_ns=end), collections) if end > start else []
    memories = [window.get('memory_before'), window.get('memory_at_restore'),
                record.get('memory_after_cleanup')]
    checks = dict(
        original_observation_complete=report['diagnostic_complete'],
        owner_identity=bool(record and record.get('owner_pid') == run.get('owner_pid')
                            and record.get('parent_pid') == run.get('parent_pid')),
        originally_enabled=window.get('original_enabled') is True,
        restored=bool(window.get('restored') and window.get('final_enabled') is True),
        thresholds_unchanged=bool(window.get('thresholds_before')
            and window.get('thresholds_before') == window.get('thresholds_after')),
        capture_covered=bool(capture['start_ns'] and 0 < start <= capture['start_ns']
                            and end >= capture['end_ns'] and end > start),
        no_collection_in_window=bool(window.get('collections_delta') == [0, 0, 0] and not inside),
        memory_available=all(bool(m and m.get('available') and m.get('rss_kib', 0) > 0
            and m.get('process_lifetime_peak_kib', -1) >= m['rss_kib']) for m in memories),
        no_wrapper_error=bool(record and not record.get('install_error')
            and not record.get('wrapper_error') and not window.get('errors')))
    valid = all(checks.values())
    summary = run.get('summary') or {}
    pilot = bool(valid and run.get('display_pilot_completed') and run.get('error') is None
        and summary.get('fault') is None and summary.get('stop_reason') == 'duration_complete'
        and summary.get('elapsed_seconds', 0) >= 60.)
    report.update(schema='effective25_gc_window_comparison_v1', controlled_experiment=True,
        gc_policy_changed_inside_window=bool(start and window.get('original_enabled') is True),
        comparison_valid=valid,
        control_checks=checks, control_pilot_completed=pilot, owner_window=window,
        memory_after_cleanup=record.get('memory_after_cleanup'),
        physical_memory_measured=all(bool(m and m.get('source') == 'proc_self_status') for m in memories),
        window_gc_intervals=inside, install_error=record.get('install_error'),
        wrapper_error=record.get('wrapper_error'),
        caveat_cn='仅本次独立所有者在预热后到工作线程退出暂缓自动循环GC，恢复后继续原收尾；Notebook和PS子进程不改。原GC日志的strategy_unchanged仅表示起止状态相同，不表示窗口内策略未变。未强制回收、未改GC阈值；25/25、算法、队列、100ms状态门、1秒结果门、2秒父心跳和停止策略不变。RSS是三个边界快照，VmHWM是进程生存期峰值，不是窗口内峰值；不据此证明长时间内存稳定。单次结果不能证明永久修复、准确率、DDR或完整V3a验收。')
    return report


def report_text(report):
    window = report['owner_window']
    before, after = window.get('memory_before') or {}, window.get('memory_at_restore') or {}
    cleanup = report.get('memory_after_cleanup') or {}
    lines = ['25/25单次GC窗口对照（不是永久修复或验收）',
        '对照证据完整：'+str(report['comparison_valid']),
        '60秒显示基础小试完成：'+str(report['control_pilot_completed']),
        'GC恢复原状态：'+(str(window.get('restored', False)) if window.get('started_ns')
                         else '未进入窗口，未暂停GC'),
        '采集时长：'+str(report['elapsed_seconds'])+' 秒',
        '原运行错误：'+str(report['capture_error']),
        '窗口内GC代数计数增量：'+str(window.get('collections_delta')),
        '所有者RSS：窗口前 '+str(before.get('rss_kib'))+' KiB；恢复前 '+str(after.get('rss_kib'))
            +' KiB；收尾后 '+str(cleanup.get('rss_kib'))+' KiB',
        '窗口前后RSS变化：'+str(window.get('rss_change_kib'))+' KiB',
        '所有者进程生存期峰值：'+str(cleanup.get('process_lifetime_peak_kib'))+' KiB']
    for key, label in (('longest_processing', '最长处理'), ('longest_read_gap', '最长采集间隔')):
        span = report[key]
        if span: lines.append('%s：%.3f ms' % (label, span['wall_ms']))
    if not report['comparison_valid']:
        lines.append('未通过的对照检查：'+str([k for k, v in report['control_checks'].items() if not v]))
        lines.append('原观测未通过项：'+str([k for k, v in report['checks'].items() if not v]))
    lines += [report['caveat_cn'],
        '请回传gc_window.json、gc_window.txt、owner_gc_window.json、owner_gc.json及原七份结果。不要自动重试。']
    return '\n'.join(lines)+'\n'
