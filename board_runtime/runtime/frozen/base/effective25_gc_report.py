"""Read-only post-cleanup correlation. Overlap is not a causal conclusion."""
import csv
from pathlib import Path


def intervals(events):
    pending, result, issues = None, [], []
    previous = -1
    for row in events:
        at = row['at_ns']
        if at < previous:
            issues.append('GC时间顺序错误')
        previous = at
        if row['phase'] == 'start':
            if pending is not None:
                issues.append('GC重复开始／遗漏结束')
            pending = row
        elif row['phase'] == 'stop':
            if pending is None:
                issues.append('GC遗漏开始')
                continue
            if (pending['generation'] != row['generation'] or pending['tid'] != row['tid']
                    or at < pending['at_ns']):
                issues.append('GC起止身份／顺序不符')
            else:
                result.append(dict(start_ns=pending['at_ns'], end_ns=at,
                    wall_ms=(at-pending['at_ns'])/1e6, generation=row['generation'],
                    tid=row['tid'], collected=row['collected'], uncollectable=row['uncollectable']))
            pending = None
        else:
            issues.append('未知GC阶段')
    if pending is not None:
        issues.append('GC最后一次未结束')
    return result, issues


def overlaps(span, collections):
    result = []
    for item in collections:
        duration = min(span['end_ns'], item['end_ns']) - max(span['start_ns'], item['start_ns'])
        if duration > 0:
            result.append(dict(item, overlap_ms=duration/1e6))
    return result


def read_timings(directory):
    issues, raw, processed = [], [], []
    for name, destination in (('raw.csv', raw), ('results.csv', processed)):
        try:
            with (Path(directory)/'capture'/name).open(encoding='utf8', newline='') as stream:
                destination.extend(csv.DictReader(stream))
        except (OSError, ValueError) as exc:
            issues.append(name+': '+str(exc))
    gaps, spans = [], []
    previous = None
    try:
        for row in raw:
            stamp = int(row['ppg_read_completed_ns'])
            if previous is not None and stamp < previous:
                issues.append('原始读取时间倒退')
            if previous is not None and stamp > previous:
                gaps.append(dict(start_ns=previous, end_ns=stamp,
                    wall_ms=(stamp-previous)/1e6, next_sequence=int(row['sequence'])))
            previous = stamp
        for row in processed:
            start, end = int(row['processing_started_ns']), int(row['processing_finished_ns'])
            if end < start:
                issues.append('处理时间倒退')
            spans.append(dict(start_ns=start, end_ns=end, sequence=int(row['sequence']),
                wall_ms=(end-start)/1e6, pl_ms=int(row['pl_call_ns'])/1e6))
    except (ValueError, KeyError) as exc:
        issues.append('记录时间字段错误：'+str(exc))
    return raw, processed, gaps, spans, issues


def assemble(directory, run, owner, changed):
    from run_effective25_gc_probe import BASE_SHA, FLAGS
    summary = run.get('summary') or {}
    isolation = summary.get('isolation') or {}
    log = owner.get('gc', {}) if owner else {}
    collections, issues = intervals(log.get('events', []))
    raw, processed, gaps, spans, read_issues = read_timings(directory)
    issues += read_issues
    start = (summary.get('startup') or {}).get('started_ns')
    end = max([r['end_ns'] for r in spans+gaps], default=0)
    covered = bool(start and end >= start and 0 < log.get('started_ns', 0) <= start
                   and log.get('finished_ns', 0) >= end)
    matched = bool(owner and owner.get('owner_pid') == run.get('owner_pid')
        and owner.get('parent_pid') == run.get('parent_pid')
        and log.get('pid') == run.get('owner_pid')
        and run.get('owner_pid') != run.get('parent_pid'))
    counts = bool(raw and processed and len(raw) == summary.get('raw_saved')
                  and len(processed) == summary.get('results_saved'))
    formal = [r for r in collections if start and r['start_ns'] <= end and r['end_ns'] >= start]
    for span in spans+gaps:
        span['owner_gc_overlaps'] = overlaps(span, collections)
    spans.sort(key=lambda r: r['wall_ms'], reverse=True)
    gaps.sort(key=lambda r: r['wall_ms'], reverse=True)
    checks = dict(owner_identity=matched, capture_window_covered=covered, saved_row_counts=counts,
        gc_recording=bool(log.get('complete') and not log.get('dropped')
            and not log.get('callback_errors') and log.get('strategy_unchanged')),
        event_and_csv_integrity=not issues, inputs_unchanged=bool(run.get('inputs_unchanged') and not changed),
        cleanup=bool(run.get('cleanup_complete') and run.get('owner_exitcode') == 0
            and isolation.get('exitcode') == 0 and isolation.get('cleanup_complete')
            and not isolation.get('forced_termination') and owner
            and owner.get('capture_cleanup_complete') and owner.get('wrapper_error') is None))
    return dict(schema='effective25_gc_probe_v1', **FLAGS, diagnostic_only=True,
        diagnostic_complete=all(checks.values()), checks=checks, issues=issues,
        root_cause_proven=False, exact_display_stop_observed=False, observed_processes=['owner'],
        base_manifest_sha256=BASE_SHA, raw_hz=25, processing_hz=25,
        elapsed_seconds=summary.get('elapsed_seconds'), stop_reason=summary.get('stop_reason'),
        capture_error=run.get('error'), capture_fault=summary.get('fault'),
        cleanup_complete=run.get('cleanup_complete', False),
        raw_saved=summary.get('raw_saved'), processed=summary.get('processed'),
        capture_window=dict(start_ns=start, end_ns=end),
        owner_gc_total_intervals=len(collections), owner_gc_capture_intervals=formal,
        owner_gc_capture_max_ms=max((r['wall_ms'] for r in formal), default=None),
        longest_processing=spans[0] if spans else None,
        longest_read_gap=gaps[0] if gaps else None,
        processing_top8=spans[:8], read_gaps_top8=gaps[:8],
        owner_gc_recording={k: v for k, v in log.items() if k != 'events'},
        inputs_unchanged=checks['inputs_unchanged'], changed_files=changed,
        caveat_cn='仅观察所有者GC；没有逐拍包装、共享跟踪数组或额外IPC。观测仍可能改变分配/调度；GC区间包含可能的调度暂停，时间重叠不单独证明因果。未观测Notebook/PS子进程GC，也未记录精确显示判定时刻。原100ms状态门、1秒结果门、2秒父心跳和停止策略不变。')


def report_text(report):
    lines = ['25/25最小GC观测（不是修复或验收）',
        '观测完整：'+str(report['diagnostic_complete']),
        '采集时长：'+str(report['elapsed_seconds'])+' 秒',
        '原运行错误：'+str(report['capture_error']),
        '正式窗口所有者GC次数：'+str(len(report['owner_gc_capture_intervals'])),
        '正式窗口最长所有者GC：'+str(report['owner_gc_capture_max_ms'])+' ms']
    for key, label in (('longest_processing', '最长处理'), ('longest_read_gap', '最长采集间隔')):
        span = report[key]
        if span:
            lines.append('%s：%.3f ms；重叠所有者GC次数：%d' %
                         (label, span['wall_ms'], len(span['owner_gc_overlaps'])))
            for row in span['owner_gc_overlaps'][:3]:
                lines.append('  GC代数%d：区间%.3f ms，重叠%.3f ms' %
                             (row['generation'], row['wall_ms'], row['overlap_ms']))
    if not report['diagnostic_complete']:
        lines.append('未通过的完整性检查：'+str([k for k, v in report['checks'].items() if not v]))
    lines.extend([report['caveat_cn'],
        '请回传gc_probe.json、gc_probe.txt、owner_gc.json及原七份结果；不要自动重试。'])
    return '\n'.join(lines)+'\n'
