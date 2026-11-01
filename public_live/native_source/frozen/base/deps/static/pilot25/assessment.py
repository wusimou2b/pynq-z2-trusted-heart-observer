"""After-close raw50/slot25 audit; diagnostics never freeze formal limits."""
import csv
import json
import math
from heart_v2.runtime_main_chain import parse_boolean
from rate25_tools.delivery import digest
from rate25_tools.reporting import distribution
from .delivery import FLAGS


def _rows(path):
    with path.open(encoding='utf8',newline='') as stream: return list(csv.DictReader(stream))


def _boolean(row,key):
    return parse_boolean(row[key],key)


def _timing(values):
    if any(not math.isfinite(v) or v < 0 for v in values):
        return dict(count=len(values),mean_ms=None,median_ms=None,p99_ms=None,max_ms=None)
    return distribution(values)


def assess(summary, paths):
    raw, rows = _rows(paths.raw_csv), _rows(paths.results_csv)
    with paths.events_jsonl.open(encoding='utf8') as stream:
        events = [json.loads(line) for line in stream if line.strip()]
    n, m = len(raw), len(rows)
    tail = summary['frontend']['pending_raw']
    forbidden = sum((not _boolean(row,'output_allowed') and bool(row['bpm'])) or
        (not _boolean(row,'publication_allowed') and bool(row['publication_bpm'])) or
        (_boolean(row,'publication_allowed') and (not _boolean(row,'output_allowed') or row['publication_bpm'] != row['bpm']))
        for row in rows)
    snapshot = summary.get('pl_snapshot') or {}
    groups = []
    for row in raw:
        if not groups or groups[-1][0] != int(row['batch_id']):
            groups.append((int(row['batch_id']),int(row['ppg_read_completed_ns']),int(row['capture_loop_ns'])))
    gaps = [right[1]-left[1] for left,right in zip(groups,groups[1:])]
    timing = {key:_timing([int(row[field]) for row in rows]) for key,field in (
        ('read_to_result','read_to_result_ns'),('processing_queue_wait','processing_queue_wait_ns'),
        ('ps_processing','ps_processing_ns'),('pl_call','pl_call_ns'))}
    timing['processing'] = _timing([int(r['processing_finished_ns'])-int(r['processing_started_ns']) for r in rows])
    timing['read_gap'] = _timing(gaps)
    paired = sum(_boolean(row,'pair_ok') for row in raw)
    front = summary['frontend']
    isolation = summary.get('isolation') or {}
    gates = dict(
        full_duration=summary['stop_reason'] == 'duration_complete' and summary['duration_seconds'] == 60.
            and summary['elapsed_seconds'] >= 60.,
        cleanup=summary['cleanup_complete'] and summary['queues_drained'],
        no_fault=summary['fault'] is None and summary['state'] == 'stopped',
        exact_counts=(n == summary['read'] == summary['raw_saved'] == summary['raw_attempted'] == summary['process_enqueued']
            and m == summary['processed'] == summary['results_saved'] == summary['results_attempted']
            and tail in (0,1) and n == 2*m+tail and summary['count_identity']
            and summary['unadapted_saved_raw'] == summary['formed_unprocessed_slots'] == 0
            and summary['unprocessed_raw'] == tail and front['raw_received'] == n
            and front['slots_emitted'] == m and front['consumed_raw'] == 2*m),
        sequence_alignment=bool(raw) and [int(r['sequence']) for r in raw] == list(range(n))
            and [int(r['sequence']) for r in rows] == list(range(m))
            and all((int(r['source_first']),int(r['source_last'])) == (2*i,2*i+1) for i,r in enumerate(rows)),
        raw_safety=summary['raw_safety'].get('raw_observed') == n and not summary['raw_safety'].get('fault'),
        flush_order=all(int(r['first_raw_saved_ns']) <= int(r['processing_started_ns'])
            and int(r['raw_saved_ns']) <= int(r['processing_started_ns']) for r in rows),
        paired=bool(n) and paired/n >= .995 and paired == summary['paired'] and n-paired == summary['unpaired'],
        no_queue_full=not any(summary['queue_full'].values()),
        formal_errors_zero=all(summary[k] == 0 for k in ('sensor_errors','pl_fifo_errors','max30102_overflow_events',
            'max30102_overflow_count','timestamp_errors','timestamp_rejected_samples','acceleration_invalid_events')),
        known_consumption=not summary['consumed_ppg_unknown'], forbidden_bpm_zero=forbidden == 0,
        real_backend=summary['board_tested'] and summary['backend_source'] == 'pl_mmio',
        event_counts=len(events) == summary['events_saved'] and sum(e.get('samples',0) for e in events if e.get('stage') == 'raw_flushed') == n,
        pl_counts=bool(rows) and snapshot.get('accepted') == snapshot.get('emitted') == m
            and snapshot.get('saturated') == 0 and snapshot.get('clipped') == sum(bool(int(r['pl_status']) & 4) for r in rows)
            and snapshot.get('max_latency_cycles') == max(int(r['pl_latency_cycles']) for r in rows)
            and all(int(r['pl_epoch']) == snapshot.get('epoch') for r in rows),
        pl_public=bool(rows) and all(r['backend_source'] == 'pl_mmio' and int(r['beta_int']) == 32212255
            and int(r['pl_sequence']) == int(r['sequence']) and 0 < int(r['pl_latency_cycles']) <= 2048
            and not int(r['pl_status']) & 8 for r in rows),
        isolation=isolation.get('completed_steps') == isolation.get('pl_requests') == m
            and isolation.get('cleanup_complete') is True and isolation.get('forced_termination') is False
            and isolation.get('exitcode') == 0 and isolation.get('worker_hardware_imported') is False,
        timing_nonnegative=all(v['count'] == 0 or v['max_ms'] is not None for v in timing.values()))
    measurements = dict(record_rate_hz=summary['record_rate_hz'],
        processing_slot_rate_hz=m/summary['elapsed_seconds'] if summary['elapsed_seconds'] > 0 else None,
        read_gap_p99_ms=timing['read_gap']['p99_ms'],read_gap_max_ms=timing['read_gap']['max_ms'],
        read_to_result_p99_ms=timing['read_to_result']['p99_ms'],read_to_result_max_ms=timing['read_to_result']['max_ms'],
        capture_loop_overrun_fraction=sum(g[2] > 20_000_000 for g in groups)/len(groups) if groups else None,
        read_to_display_p99_ms=None,read_to_display_max_ms=None)
    summary.update(**FLAGS, static_pilot_completed=all(gates.values()),display_measured=False,display=None,
        limits_sha256=None,performance_limits_validated=False,measurements=measurements,timing25=timing,
        audit25=dict(raw_rows=n,result_rows=m,pending_raw=tail,forbidden_bpm_rows=forbidden,
                     gates={k:bool(v) for k,v in gates.items()}),
        raw_sha256=digest(paths.raw_csv),results_sha256=digest(paths.results_csv),events_sha256=digest(paths.events_jsonl),
        pilot_scope_cn='本次静止无绘图基础检查，不是完整实时/显示/准确率/DDR验收；性能限值未冻结。')
    return summary
