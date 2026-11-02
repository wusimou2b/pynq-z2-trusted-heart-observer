"""Cold package guard and independent startup-overlap/lifetime audit."""
import json
from pathlib import Path

if __package__:
    from .joint_startup_guard import verify_startup as verify_base,assess_startup,sha,write_new,notebook_code_hash,FLAGS
    from .joint_concurrent_guard import assess_concurrent
else:
    from joint_startup_guard import verify_startup as verify_base,assess_startup,sha,write_new,notebook_code_hash,FLAGS
    from joint_concurrent_guard import assess_concurrent

BASE_SHA='6bef89e94da1eb68c79031750016ecba3214b2bfe994465b15adf21ae4412f4f'
EXTRAS={'joint_overlap.py','joint_overlap_worker.py','joint_overlap_guard.py','run_joint_overlap.py','README_OVERLAP5.md'}
NOTEBOOK='JointOverlap5.ipynb'
MANIFEST='joint-overlap-manifest.json'
IDENTITY=dict(entry_variant='effective25_entry6_static_v1',entry_confirmation_checks=6,
    entry_candidate_sha256='8781385123c7a97c9273ee7aa69c27eaf2bb0f75655eb23a7f18a1ba323e8c47',
    entry_manifest_sha256='00879aa1d75813cdbc1cb644706b369e465615cb340c6a739b67e5fd9fa3adf8')


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_overlap(root):
    root=Path(root);base=verify_base(root)
    if sha(root/'joint-startup-manifest.json')!=BASE_SHA:raise ValueError('reviewed startup package changed')
    doc=read(root/MANIFEST)
    if (doc.get('schema')!='v3b25_overlap5_package_v1' or set(doc.get('files',{}))!=EXTRAS or
        doc.get('base_manifest_sha256')!=BASE_SHA or
        tuple(doc.get(k) for k in ('raw_hz','processing_hz','video_target_fps','formal_seconds','startup_timeout_seconds','warmup_slots'))!=(25,25,5,60,90,700) or
        doc.get('startup_speed_improved_verified') is not False or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('overlap scope/file/flags changed')
    for name,digest in doc['files'].items():
        path=root/name
        if path.is_symlink() or not path.is_file() or sha(path)!=digest:raise ValueError('overlap file changed: '+name)
    if notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):raise ValueError('overlap Notebook code changed')
    return dict(base,overlap_manifest_sha256=sha(root/MANIFEST),warmup_slots=700)


def assess_overlap(directory,startup):
    directory=Path(directory)
    checks=dict(ledger=False,owner_hash=False,original_trial=False,ready=False,one_bridge=False,
        adoption=False,overlap=False,ownership=False,cleanup=False,natural_exit=False)
    result=dict(schema='v3b25_overlap5_trial_v1',checks=checks,error=None,overlap_ns=0,overlap_observed=False,
        overlap_candidate_completed=False,joint_60s_pilot_completed=False,startup_speed_improved_verified=False,**FLAGS,
        scope_cn='原700点纯PS预热与硬件准备重叠候选；原90秒/25,25Hz/5fps/保护不变。不是严格实时、准确率、15fps或DDR验收。')
    try:
        warm=read(directory/'owner_overlap.json');run=read(directory/'run_entry25_live.json')
        owner=read(directory/'concurrent_owner_result.json');joint=read(directory/'joint_concurrent_result.json')
        summary=run.get('summary') or {};epoch=(summary.get('startup') or {}).get('started_ns')
        again=assess_concurrent(directory,run,owner,inputs_unchanged=startup.get('inputs_unchanged') is True)
        ledger=assess_startup(directory,joint,formal_epoch=epoch)
        checks['ledger']=bool(ledger['startup_observation_complete'] and
            all(ledger[k]==startup.get(k) for k in ('checks','cancelled','phase_intervals','owner_entry_to_formal_ns')))
        checks['original_trial']=bool(startup.get('joint_60s_pilot_completed') is True and startup.get('wrapper_error') is None and
            joint.get('joint_60s_pilot_completed') is True and again['joint_60s_pilot_completed'] and again['checks']==joint.get('checks'))
        checks['owner_hash']=(startup.get('input_sha256') or {}).get('owner_overlap.json')==sha(directory/'owner_overlap.json')
        trace=read(directory/'owner_startup.json')
        rows=[json.loads(s) for s in (directory/'startup_events.jsonl').read_text(encoding='utf-8').splitlines()]
        r=warm.get('ready_info') or {};final=warm.get('final_info') or {};pid=r.get('worker_pid')
        checks['ready']=bool(warm.get('schema')=='v3b25_overlap_owner_v1' and warm.get('source')=='pl_mmio' and
            warm.get('owner_pid')==trace.get('owner_pid') and warm.get('expected_identity')==IDENTITY and
            all(r.get(k)==v for k,v in IDENTITY.items()) and r.get('worker_hardware_imported') is False and
            r.get('ps_gc_enabled_at_ready') is True and (r.get('warmup_raw'),r.get('warmup_slots'))==(700,700) and
            r.get('completed_steps')==r.get('pl_requests')==0 and r.get('forced_termination') is False and r.get('exitcode') is None and
            type(pid) is int and pid>0 and pid!=warm.get('owner_pid') and pid==(summary.get('isolation') or {}).get('worker_pid')==final.get('worker_pid'))
        checks['one_bridge']=bool(warm.get('attempted') is True and warm.get('bridge_created')==warm.get('claims')==1 and
            warm.get('constructor_completed') is True and warm.get('ready_verified') is True and warm.get('error') is None)
        def span(name):
            intervals=[v for v in trace['phase_intervals'] if v['phase']==name and v['outcome']=='end']
            if len(intervals)!=1:raise ValueError('startup phase missing/duplicate: '+name)
            interval=intervals[0];return rows[interval['begin_index']]['at_ns'],rows[interval['end_index']]['at_ns']
        w0,w1=span('ps_warmup');p0,p1=span('joint_prepare');a0,a1=span('session_ready_bridge_wait')
        overlap=max(0,min(w1,p1)-max(w0,p0));result['overlap_ns']=overlap
        checks['overlap']=bool(checks['ledger'] and overlap>0 and p1<=epoch and w1<=epoch)
        adopted=[v for v in rows if v['phase']=='ps_bridge_adopt' and v['kind']=='stage']
        checks['adoption']=bool(len(adopted)==1 and not adopted[0]['stop_requested'] and
            adopted[0]['details']==dict(worker_pid=pid,source='pl_mmio') and
            w1<=adopted[0]['at_ns']<=epoch and a0<=adopted[0]['at_ns']<=a1)
        checks['ownership']=warm.get('session_attached') is True and warm.get('untransferred_closed') is False
        checks['cleanup']=bool(warm.get('disposed') is True and warm.get('cleanup_complete') is True and
            warm.get('thread_alive') is False and warm.get('ps_child_alive') is False and
            warm.get('cleanup_error') is None and warm.get('final_info_error') is None and
            owner.get('retention_reasons')==[] and owner.get('actual_lease_released') is True)
        checks['natural_exit']=bool(final.get('forced_termination') is False and final.get('exitcode')==0 and
            final.get('cleanup_complete') is True and
            final.get('completed_steps')==final.get('pl_requests')==summary.get('read',-1))
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc))
    result['overlap_observed']=checks['overlap']
    result['overlap_candidate_completed']=result['joint_60s_pilot_completed']=all(checks.values())
    return result
