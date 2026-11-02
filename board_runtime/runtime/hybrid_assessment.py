"""Keep original browser/manual audit and append submitted HDMI text evidence."""
import json
from pathlib import Path

if __package__:
    from .shadow_assessment import audit_shadow_artifacts as base_audit,_CsvCursor
else:
    from shadow_assessment import audit_shadow_artifacts as base_audit,_CsvCursor


def audit_text(directory):
    directory=Path(directory);rows=numeric=0;errors=[]
    try:
        with (directory/'capture/raw.csv').open(encoding='utf-8',newline='') as raw, \
             (directory/'capture/results.csv').open(encoding='utf-8',newline='') as results, \
             (directory/'video/frames.jsonl').open(encoding='utf-8') as video:
            raw_cursor,result_cursor=_CsvCursor(raw),_CsvCursor(results)
            for line in video:
                row=json.loads(line);p=row['hybrid'];rows+=1
                if not(p['layout']=='camera_bpm_strip_v1' and p['hdmi_curve_count']==0
                    and p['browser_graphics_enabled'] is True and p['checked_ns']<=row['submitted_ns']):
                    raise ValueError('hybrid layout/time differs')
                if p['bpm_text']=='N/A':continue
                r=raw_cursor.get(p['sequence']);s=result_cursor.get(p['sequence'])
                if not(p['eligible'] is True and p['historical'] is False
                    and 0<=p['status_age_ns']<=100_000_000
                    and 0<=p['checked_ns']-p['source_read_ns']<=1_000_000_000
                    and int(r['ppg_read_completed_ns'])==p['source_read_ns']
                    and s['output_allowed']=='True' and format(float(s['bpm']),'.1f')==p['bpm_text']):
                    raise ValueError('hybrid numeric source/freshness differs')
                numeric+=1
        owner=json.loads((directory/'hybrid-owner.json').read_text('utf-8'))
        if not(owner['inputs_unchanged'] and owner['wrapper_error'] is None
            and owner['video_writer_stopped'] and owner['binding_instances']==1
            and owner['display']['submitted_frames']==rows):raise ValueError('hybrid owner/row count differs')
    except Exception as exc:errors.append(dict(type=type(exc).__name__,message=str(exc),at_row=rows))
    return dict(passed=rows>0 and not errors,rows=rows,numeric_rows=numeric,errors=errors,
        scope='submitted text/source evidence; physical display and accuracy not measured')


def audit_artifacts(directory,summary,owner):
    result=base_audit(directory,summary,owner)
    if not result.get('journals_read'):return result
    audit=audit_text(directory)
    result['checks']['hdmi_text_source_audit']=audit['passed']
    result.update(hybrid=audit,browser_graphics_enabled=True)
    return result
