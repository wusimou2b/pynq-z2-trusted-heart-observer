"""Reuse display-only audit, not predecessor raw50 count assertions."""
from copy import deepcopy
from display25.assessment import display_audit
from .assessment import assess as assess_capture, rows, timing


def assess(summary,paths):
    display=deepcopy(summary.get('display'))
    summary=assess_capture(summary,paths)
    result=rows(paths.results_csv)
    gates=display_audit(display,result)
    samples=(display or {}).get('samples',[])
    attempts=(display or {}).get('attempts',[])
    delay=timing([s['read_to_display_ns'] for s in samples])
    ends=[s['refresh_completed_ns'] for s in samples]
    capture_ok=summary['static_pilot_completed']
    summary.update(display=display,display_measured=bool(samples),browser_display_measured=False,
        display_measurement_scope='kernel_publish',capture_basics_completed=capture_ok,
        static_pilot_completed=False,display_pilot_completed=bool(capture_ok and all(gates.values())),
        display_audit=dict(gates=gates,refresh_samples=len(samples),attempts=len(attempts),
            sample_span_seconds=(ends[-1]-ends[0])/1e9 if len(ends)>1 else 0.,
            max_refresh_gap_ms=max((b-a for a,b in zip(ends,ends[1:])),default=0)/1e6),
        display_timing=delay)
    summary['bpm_evidence']['numeric_display_attempts']=sum(a['success'] and a['bpm_text']!='N/A' for a in attempts)
    summary['measurements'].update(read_to_display_p99_ms=delay['p99_ms'],read_to_display_max_ms=delay['max_ms'])
    return summary
