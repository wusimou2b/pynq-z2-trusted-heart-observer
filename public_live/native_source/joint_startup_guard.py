"""Cold identity and startup-ledger checks, separate from the original joint audit."""
import json
from pathlib import Path

if __package__:
    from .joint_concurrent_guard import verify_concurrent,FLAGS,sha,write_new,notebook_code_hash
else:
    from joint_concurrent_guard import verify_concurrent,FLAGS,sha,write_new,notebook_code_hash

BASE_SHA='e0634a04593dba3085bbd8a2c625602fb4ba8cf03a613a7d75cea51db2267728'
EXTRAS={'joint_startup.py','joint_startup_worker.py','joint_startup_guard.py','run_joint_startup.py','README_STARTUP5.md'}
MANIFEST='joint-startup-manifest.json'
NOTEBOOK='JointStartup5.ipynb'


def verify_startup(root):
    root=Path(root);base=verify_concurrent(root)
    if sha(root/'joint-concurrent-manifest.json')!=BASE_SHA:raise ValueError('reviewed concurrent base changed')
    doc=json.loads((root/MANIFEST).read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_startup5_package_v1' or set(doc.get('files',{}))!=EXTRAS or
        doc.get('base_manifest_sha256')!=BASE_SHA or
        (doc.get('raw_hz'),doc.get('processing_hz'),doc.get('video_target_fps'),doc.get('formal_seconds'),doc.get('startup_timeout_seconds'))!=(25,25,5,60,90) or
        doc.get('startup_speed_improved_verified') is not False or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('startup scope/file/flags changed')
    for name,digest in doc['files'].items():
        p=root/name
        if p.is_symlink() or not p.is_file() or sha(p)!=digest:raise ValueError('startup file changed: '+name)
    if notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):raise ValueError('startup Notebook code changed')
    return dict(base,startup_manifest_sha256=sha(root/MANIFEST),startup_timeout_seconds=90,
        startup_speed_improved_verified=False)


def assess_startup(directory,joint,*,formal_epoch=None):
    directory=Path(directory)
    checks=dict(trace_hash=False,ledger=False,intervals=False,cancellation=False,formal_epoch=False)
    result=dict(schema='v3b25_startup5_observation_v1',checks=checks,cancelled=None,error=None,
        startup_observation_complete=False,joint_60s_pilot_completed=False,startup_speed_improved_verified=False,
        owner_entry_to_formal_ns=None,phase_intervals=[],**FLAGS,
        scope_cn='启动分段观测与停止请求门；嵌套区间不可相加。不是启动加速、60秒并发、准确率、15fps或DDR验收。')
    try:
        report=json.loads((directory/'owner_startup.json').read_text(encoding='utf-8'))
        path=directory/'startup_events.jsonl';rows=[json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
        checks['trace_hash']=sha(path)==report.get('events_sha256')
        checks['ledger']=bool(len(rows)>=2 and report.get('schema')=='v3b25_owner_startup_v1' and
            report.get('trace_closed') is True and report.get('startup_speed_improved_verified') is False and
            report.get('events_count')==len(rows) and [r['index'] for r in rows]==list(range(len(rows))) and
            all(type(r['at_ns']) is int and type(r['stop_requested']) is bool and
                r['owner_pid']==report.get('owner_pid') for r in rows) and
            all(b['at_ns']>=a['at_ns'] for a,b in zip(rows,rows[1:])) and
            rows[0]['phase']=='worker' and rows[0]['kind']=='entry' and
            rows[-1]['phase']=='worker' and rows[-1]['kind']=='finish' and
            report['started_ns']<=rows[0]['at_ns'] and report['finished_ns']==rows[-1]['at_ns'] and
            report['elapsed_ns']==report['finished_ns']-report['started_ns'])
        stacks={};intervals=[];unmatched=[]
        for row in rows:
            phase,kind=row['phase'],row['kind']
            if kind=='begin':stacks.setdefault(phase,[]).append(row)
            elif kind in ('end','error'):
                if not stacks.get(phase):unmatched.append(row['index']);continue
                start=stacks[phase].pop();intervals.append(dict(phase=phase,begin_index=start['index'],end_index=row['index'],
                    outcome=kind,elapsed_ns=row['at_ns']-start['at_ns']))
        checks['intervals']=not unmatched and intervals==report.get('phase_intervals') and \
            [r['index'] for items in stacks.values() for r in items]==report.get('unpaired_begins')
        cancelled=[r for r in rows if r['kind']=='cancelled']
        expected=dict(phase=cancelled[0]['phase'],at_ns=cancelled[0]['at_ns']) if cancelled else None
        epochs=[r for r in rows if r['phase']=='formal_epoch' and r['kind']=='observed']
        checks['cancellation']=report.get('cancelled')==expected and all(r['stop_requested'] for r in cancelled) and not (
            cancelled and any(r['index']>cancelled[0]['index'] for r in epochs))
        checks['formal_epoch']=bool(len(epochs)<=1 and (formal_epoch is None or
            len(epochs)==1 and epochs[0]['details'].get('started_ns')==formal_epoch) and
            all(type(r['details'].get('started_ns')) is int and
                report['started_ns']<=r['details']['started_ns']<=r['at_ns'] for r in epochs))
        result.update(cancelled=expected,phase_intervals=intervals,
            owner_entry_to_formal_ns=epochs[0]['details']['started_ns']-report['started_ns'] if epochs else None)
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc))
    result['startup_observation_complete']=all(checks.values())
    result['joint_60s_pilot_completed']=bool(result['startup_observation_complete'] and result['cancelled'] is None and
        result['owner_entry_to_formal_ns'] is not None and joint.get('joint_60s_pilot_completed') is True)
    return result
