"""After-close evidence. Effective FIFO records/results/PL packets are 1:1."""
import csv
import hashlib
import json
import math
from collections import Counter
from heart_v2.runtime_main_chain import parse_boolean
from rate25_tools.reporting import distribution
from .policy import validate_registers

FLAGS=dict.fromkeys(('live_25hz_passed','live_50hz_passed','auto_beta_effect_passed',
    'board_ddr_verified','limits_frozen','run_acceptance_passed','v3a_complete'),False)


def rows(path):
    with path.open(encoding='utf8',newline='') as stream: return list(csv.DictReader(stream))


def boolean(row,name): return parse_boolean(row[name],name)


def timing(values):
    if any(not math.isfinite(v) or v<0 for v in values):
        return dict(count=len(values),mean_ms=None,median_ms=None,p99_ms=None,max_ms=None)
    return distribution(values)


def assess(summary,paths):
    raw,result=rows(paths.raw_csv),rows(paths.results_csv)
    with paths.events_jsonl.open(encoding='utf8') as stream:
        events=[json.loads(line) for line in stream if line.strip()]
    n,m=len(raw),len(result)
    front=summary['frontend']; pl=summary.get('pl_snapshot') or {}; ipc=summary.get('isolation') or {}
    forbidden=numeric=published=0
    for row in result:
        allowed,publication=boolean(row,'output_allowed'),boolean(row,'publication_allowed')
        bpm=row['bpm']; published_bpm=row['publication_bpm']
        valid_bpm=bool(bpm) and math.isfinite(float(bpm)) and 40<=float(bpm)<=200
        forbidden+=int((not allowed and bool(bpm)) or (allowed and not valid_bpm)
            or (not publication and bool(published_bpm))
            or (publication and (not allowed or published_bpm!=bpm)))
        numeric+=int(allowed and valid_bpm); published+=int(publication and valid_bpm)
    groups=[]
    for row in raw:
        if not groups or groups[-1][0]!=int(row['batch_id']):
            groups.append((int(row['batch_id']),int(row['ppg_read_completed_ns']),int(row['capture_loop_ns'])))
    times={key:timing([int(r[field]) for r in result]) for key,field in (
        ('read_to_result','read_to_result_ns'),('processing_queue_wait','processing_queue_wait_ns'),
        ('ps_processing','ps_processing_ns'),('pl_call','pl_call_ns'))}
    times['processing']=timing([int(r['processing_finished_ns'])-int(r['processing_started_ns']) for r in result])
    times['read_gap']=timing([b[1]-a[1] for a,b in zip(groups,groups[1:])])
    paired=sum(boolean(r,'pair_ok') for r in raw)
    try: configured=validate_registers(summary.get('preflight',{}).get('sensor_registers',{}))
    except ValueError: configured=False
    gates=dict(
        full_duration=summary['stop_reason']=='duration_complete' and summary['duration_seconds']==60.
            and summary['elapsed_seconds']>=60.,
        cleanup=summary['cleanup_complete'] and summary['queues_drained'],
        no_fault=summary['fault'] is None and summary['state']=='stopped',
        exact_counts=(n==summary['read']==summary['raw_saved']==summary['raw_attempted']==summary['process_enqueued']
            and n==m==summary['processed']==summary['results_saved']==summary['results_attempted']
            and front['raw_received']==front['slots_emitted']==front['consumed_raw']==n
            and summary['consumed_raw_by_results']==m and front['pending_raw']==0
            and summary['unprocessed_raw']==summary['unadapted_saved_raw']==summary['formed_unprocessed_slots']==0
            and summary['count_identity']),
        sequence_alignment=bool(raw) and [int(r['sequence']) for r in raw]==list(range(n))
            and [int(r['sequence']) for r in result]==list(range(m))
            and all(int(r['source_first'])==int(r['source_last'])==i for i,r in enumerate(result)),
        sensor_configuration=configured and summary['raw_hz']==summary['processing_hz']==25
            and summary['adc_hz']==50 and summary['fifo_sample_average']==2,
        raw_safety=summary['raw_safety']['raw_observed']==n and not summary['raw_safety']['fault'],
        flush_order=all(int(r['first_raw_saved_ns'])==int(r['raw_saved_ns'])<=int(r['processing_started_ns']) for r in result),
        paired=bool(n) and paired/n>=.995 and paired==summary['paired'] and n-paired==summary['unpaired'],
        no_queue_full=not any(summary['queue_full'].values()),
        formal_errors_zero=all(summary[k]==0 for k in ('sensor_errors','pl_fifo_errors','max30102_overflow_events',
            'max30102_overflow_count','timestamp_errors','timestamp_rejected_samples','acceleration_invalid_events')),
        known_consumption=not summary['consumed_ppg_unknown'],forbidden_bpm_zero=forbidden==0,
        real_backend=summary['board_tested'] and summary['backend_source']=='pl_mmio',
        event_counts=len(events)==summary['events_saved']
            and sum(e.get('samples',0) for e in events if e.get('stage')=='raw_flushed')==n,
        pl_counts=bool(m) and pl.get('accepted')==pl.get('emitted')==m and pl.get('saturated')==0
            and pl.get('clipped')==sum(bool(int(r['pl_status'])&4) for r in result)
            and pl.get('max_latency_cycles')==max(int(r['pl_latency_cycles']) for r in result)
            and all(int(r['pl_epoch'])==pl.get('epoch') for r in result),
        pl_public=bool(m) and all(r['backend_source']=='pl_mmio' and int(r['beta_int'])==32212255
            and int(r['pl_sequence'])==int(r['sequence']) and 0<int(r['pl_latency_cycles'])<=2048
            and not int(r['pl_status'])&8 for r in result),
        isolation=ipc.get('completed_steps')==ipc.get('pl_requests')==m and ipc.get('cleanup_complete') is True
            and ipc.get('forced_termination') is False and ipc.get('exitcode')==0 and ipc.get('worker_hardware_imported') is False,
        timing_nonnegative=all(v['count']==0 or v['max_ms'] is not None for v in times.values()))
    summary.update(**FLAGS,static_pilot_completed=bool(all(gates.values())),
        capture_basics_completed=bool(all(gates.values())),display_pilot_completed=False,
        performance_limits_validated=False,limits_sha256=None,timing25=times,
        audit25=dict(raw_rows=n,result_rows=m,pending_raw=0,forbidden_bpm_rows=forbidden,
                     gates={k:bool(v) for k,v in gates.items()}),
        bpm_evidence=dict(numeric_rows=numeric,publication_rows=published,
            trusted_bpm_observed=numeric>0,accuracy_verified=False,
            no_output_reasons=dict(Counter(r['reason_cn'] for r in result if not boolean(r,'output_allowed')))),
        measurements=dict(record_rate_hz=summary['record_rate_hz'],
            processing_slot_rate_hz=m/summary['elapsed_seconds'] if summary['elapsed_seconds']>0 else None,
            read_gap_p99_ms=times['read_gap']['p99_ms'],read_gap_max_ms=times['read_gap']['max_ms'],
            read_to_result_p99_ms=times['read_to_result']['p99_ms'],read_to_result_max_ms=times['read_to_result']['max_ms'],
            capture_loop_overrun_fraction=sum(g[2]>40_000_000 for g in groups)/len(groups) if groups else None,
            read_to_display_p99_ms=None,read_to_display_max_ms=None),
        pilot_scope_cn='25Hz有效输入/处理的新前端基线；基础通过不等于可信心率、准确率、DDR或完整验收。')
    for key,path in (('raw',paths.raw_csv),('results',paths.results_csv),('events',paths.events_jsonl)):
        summary[key+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    return summary
