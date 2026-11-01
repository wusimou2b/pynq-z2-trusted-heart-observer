"""Keep capture and display evidence separate. No formal limits are frozen."""
from copy import deepcopy
import csv
import math
from pilot25.assessment import assess as assess_capture
from rate25_tools.reporting import distribution


def display_audit(display, rows):
    data = display or {}
    samples,attempts = data.get('samples',[]),data.get('attempts',[])
    by_sequence = {int(r['sequence']):r for r in rows}
    samples_ok = attempts_ok = True
    previous = None
    for sample in samples:
        row = by_sequence.get(sample['sequence'])
        end,read = sample['refresh_completed_ns'],sample['read_completed_ns']
        samples_ok &= bool(row is not None and int(row['ppg_read_completed_ns']) == read
            and end-read == sample['read_to_display_ns'] >= 0 and sample['render_ns'] >= 0
            and (previous is None or end >= previous))
        previous = end
        samples_ok &= any(a['success'] and a['sequence'] == sample['sequence']
            and a['read_completed_ns'] == read and a['bpm_text'] == sample['bpm_text']
            and a['historical'] == sample['historical'] and a['completed_ns'] <= end for a in attempts)
    for attempt in attempts:
        start,end = attempt['at_ns'],attempt['completed_ns']
        attempts_ok &= 0 <= start <= end
        seq,read = attempt['sequence'],attempt['read_completed_ns']
        row = by_sequence.get(seq)
        if seq is not None:
            attempts_ok &= bool(row is not None and int(row['ppg_read_completed_ns']) == read)
        if attempt['bpm_text'] != 'N/A':
            bpm = attempt['frame_bpm']
            attempts_ok &= bool(row is not None and row['output_allowed'] == 'True'
                and attempt['state'] == 'running' and not attempt['faulted'] and not attempt['historical']
                and attempt['frame_allowed'] and attempt['contact_ready']
                and attempt['slot_generation'] == attempt['safety_generation'] == int(row['generation'])
                and bpm is not None and math.isfinite(bpm) and 0 <= start-read <= 1_000_000_000
                and attempt['bpm_text'] == format(bpm,'.1f') == format(float(row['bpm']),'.1f'))
    final = attempts[-1] if attempts else {}
    gates = dict(samples_present=bool(samples),samples_bound=bool(samples_ok),
        attempts_valid=bool(attempts) and bool(attempts_ok),
        no_display_errors=data.get('display_errors') == 0 and not data.get('error')
            and data.get('loop_error') is None and all(a['success'] and not a['error'] for a in attempts),
        final_clear=data.get('final_clear_published') is True and final.get('success') is True
            and final.get('bpm_text') == 'N/A' and final.get('historical') is True,
        kernel_scope=data.get('measurement_scope') == 'kernel_publish')
    return gates


def assess(summary,paths):
    display = deepcopy(summary.get('display'))
    summary = assess_capture(summary,paths)
    capture_ok = summary['static_pilot_completed']
    with paths.results_csv.open(encoding='utf8',newline='') as stream: rows = list(csv.DictReader(stream))
    gates = display_audit(display,rows)
    samples = (display or {}).get('samples',[])
    delays = [s['read_to_display_ns'] for s in samples]
    valid = all(isinstance(n,int) and n >= 0 for n in delays)
    timing = distribution(delays) if valid else dict(count=len(delays),mean_ms=None,median_ms=None,p99_ms=None,max_ms=None)
    ends = [s['refresh_completed_ns'] for s in samples]
    gaps = [b-a for a,b in zip(ends,ends[1:])]
    summary.update(display=display,display_measured=bool(samples),browser_display_measured=False,
        display_measurement_scope='kernel_publish',capture_basics_completed=capture_ok,
        static_pilot_completed=False,display_pilot_completed=bool(capture_ok and all(gates.values())),
        display_audit=dict(gates=gates,refresh_samples=len(samples),attempts=len((display or {}).get('attempts',[])),
            sample_span_seconds=(ends[-1]-ends[0])/1e9 if len(ends)>1 else 0.,
            max_refresh_gap_ms=max(gaps)/1e6 if gaps else None),
        display_timing=timing,
        pilot_scope_cn='60秒静止并发Notebook发送基础检查；不是浏览器实际绘制/准确率/运动效果/DDR或完整实时验收。')
    summary['measurements'].update(read_to_display_p99_ms=timing['p99_ms'],read_to_display_max_ms=timing['max_ms'])
    return summary
