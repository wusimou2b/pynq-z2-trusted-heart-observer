"""Cold package identity and independent common-window/journal evidence checks."""
import csv
import json
import math
from pathlib import Path

if __package__:
    from .joint_heart_guard import verify_package as verify_heart,PAIR_HASHES,sha,write_new,notebook_code_hash
    from .joint_video_pack_guard import verify_pack,assess_pack,audit_pack,FLAGS
else:
    from joint_heart_guard import verify_package as verify_heart,PAIR_HASHES,sha,write_new,notebook_code_hash
    from joint_video_pack_guard import verify_pack,assess_pack,audit_pack,FLAGS

HEART_SHA='3f2170941f20de3104f71bbdfed5c0eaa258d9a6dffaf203576877dc71929d97'
PACK_SHA='a36b55568976e4e3ffdb858e8bcb48172ee34928001304b3aaaaad7a8c9ccea6'
EXTRAS={'joint_shared_video.py','joint_video_five.py','joint_concurrent_binding.py','joint_concurrent_owner.py',
    'joint_concurrent_worker.py','joint_concurrent_guard.py','run_joint_concurrent5.py','README_CONCURRENT5.md'}
NOTEBOOK='JointConcurrent5.ipynb'
MANIFEST='joint-concurrent-manifest.json'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_concurrent(root):
    root=Path(root);heart=verify_heart(root);video=verify_pack(root)
    if sha(root/'joint-heart-manifest.json')!=HEART_SHA or sha(root/'video-pack-manifest.json')!=PACK_SHA:
        raise ValueError('reviewed heart/video manifests changed')
    expected=set(read(root/'joint-heart-manifest.json')['files'])|set(read(root/'video-pack-manifest.json')['files'])
    expected|={'joint-heart-manifest.json','video-pack-manifest.json'}|EXTRAS
    doc=read(root/MANIFEST)
    if (doc.get('schema')!='v3b25_concurrent5_package_v1' or set(doc.get('files',{}))!=expected
        or (doc.get('raw_hz'),doc.get('processing_hz'),doc.get('video_target_fps'),doc.get('formal_seconds'))!=(25,25,5,60)
        or doc.get('display_mode')!='notebook_heart_hdmi_vision' or doc.get('shared_actual_owner') is not True
        or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('concurrent scope/file/flags changed')
    for name,digest in doc['files'].items():
        p=root/name
        if p.is_symlink() or not p.is_file() or sha(p)!=digest:raise ValueError('concurrent file changed: '+name)
    if notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):
        raise ValueError('concurrent executable Notebook changed')
    return dict(bundle_validated=True,hardware_accessed=False,frozen_files_verified=heart['frozen_files_verified'],
        package_manifest_sha256=sha(root/MANIFEST),packing_manifest_sha256=video['packing_manifest_sha256'],
        raw_hz=25,processing_hz=25,video_target_fps=5,formal_seconds=60,joint_60s_pilot_completed=False,**FLAGS)


def boolean(row,name):
    value=str(row[name]).lower()
    if value not in {'true','false','1','0'}:raise ValueError('invalid boolean: '+name)
    return value in {'true','1'}


def heart_audit(directory,summary):
    checks=dict(summary_identity=False,hashes=False,counts=False,sequence=False,raw_safety=False,
        forbidden_bpm=False,pl_public=False,events=False,timestamps=False)
    result=dict(checks=checks,raw_rows=0,result_rows=0,error=None,measurements=summary.get('measurements'))
    try:
        directory=Path(directory)/'capture'
        checks['summary_identity']=read(directory/'summary.json')==summary
        with (directory/'raw.csv').open(encoding='utf-8',newline='') as f:raw=list(csv.DictReader(f))
        with (directory/'results.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.DictReader(f))
        events=[json.loads(s) for s in (directory/'events.jsonl').read_text(encoding='utf-8').splitlines()]
        n=len(raw);m=len(rows);result.update(raw_rows=n,result_rows=m)
        checks['hashes']=all(sha(directory/name)==summary.get(key+'_sha256')
            for key,name in [('raw','raw.csv'),('results','results.csv'),('events','events.jsonl')])
        checks['counts']=bool(n and n==m and all(summary.get(k)==n for k in
            ('read','raw_saved','raw_attempted','process_enqueued','processed','results_saved','results_attempted'))
            and all(summary.get(k)==0 for k in ('unsaved_raw','unprocessed_raw','unsaved_results')))
        checks['sequence']=bool(n and [int(r['sequence']) for r in raw]==list(range(n)) and
            all(int(r['sequence'])==int(r['source_first'])==int(r['source_last'])==i for i,r in enumerate(rows)))
        paired=sum(boolean(r,'pair_ok') for r in raw)
        checks['raw_safety']=bool(n and paired/n>=.995 and paired==summary.get('paired') and n-paired==summary.get('unpaired')
            and all(not r['error'] and int(r['max30102_overflow'])==0 and
                (not boolean(r,'pair_ok') or boolean(r,'accel_valid') and boolean(r,'pl_fifo_ok')) for r in raw))
        forbidden=0
        for row in rows:
            allowed,published=boolean(row,'output_allowed'),boolean(row,'publication_allowed')
            bpm,pub=row['bpm'],row['publication_bpm']
            valid=bool(bpm) and math.isfinite(float(bpm)) and 40<=float(bpm)<=200
            forbidden+=int((not allowed and bool(bpm)) or (allowed and not valid) or
                (not published and bool(pub)) or (published and (not allowed or pub!=bpm)))
        checks['forbidden_bpm']=forbidden==0;result['forbidden_bpm_rows']=forbidden
        pl=summary.get('pl_snapshot') or {}
        checks['pl_public']=bool(m and pl.get('accepted')==pl.get('emitted')==m and pl.get('saturated')==0
            and pl.get('clipped')==sum(bool(int(r['pl_status'])&4) for r in rows)
            and pl.get('max_latency_cycles')==max(int(r['pl_latency_cycles']) for r in rows)
            and all(r['backend_source']=='pl_mmio' and int(r['pl_sequence'])==int(r['sequence'])
                and int(r['pl_epoch'])==pl.get('epoch') and int(r['beta_int'])==32212255
                and 0<int(r['pl_latency_cycles'])<=2048 and not int(r['pl_status'])&8 for r in rows))
        checks['events']=len(events)==summary.get('events_saved') and sum(
            e.get('samples',0) for e in events if e.get('stage')=='raw_flushed')==n
        epoch=summary['startup']['started_ns'];times=[int(r['ppg_read_completed_ns']) for r in raw]
        checks['timestamps']=bool(n and all(b>=a for a,b in zip(times,times[1:])) and
            epoch<=times[0]<=times[-1]<=epoch+math.ceil(summary['elapsed_seconds']*1e9))
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc))
    return result


def video_audit(directory,report,epoch):
    result=audit_pack(Path(directory)/'video',report);checks=result['checks']
    checks.update(common_window=False,grab_ledger=False,admission=False,coverage_60=False)
    try:
        rows=[json.loads(s) for s in (Path(directory)/'video/frames.jsonl').read_text(encoding='utf-8').splitlines()]
        m=report['metrics'];start=report['formal_started_ns'];deadline=report['formal_deadline_ns'];n=len(rows)
        checks['common_window']=bool(type(epoch) is int and start==epoch and deadline==epoch+60_000_000_000
            and report['requested_formal_seconds']==60 and report['target_application_fps']==5)
        formal=sum(r['submitted_ns']<=deadline for r in rows)
        elapsed=m['formal_elapsed_seconds'];fps=formal/elapsed if elapsed>0 else 0
        checks['rate']=bool(elapsed>0 and abs(m['application_submit_fps']-fps)<1e-9 and
            report.get('target_5fps_observed')==(fps>=5) and report.get('target_15fps_observed')==(fps>=15)
            and m['formal_submitted_frames']==formal and m['tail_completed_frames']==n-formal)
        grabs=[r['camera_grab_sequence'] for r in rows];slots=[r['target_slot'] for r in rows]
        checks['grab_ledger']=bool(n and report['grabs_are_exposure_counter'] is False and
            m['selected_grabs']==n and m['grabs_total']==m['preparation_grabs']+m['formal_grabs']+m['terminal_grabs']
            and m['formal_grabs']==m['selected_grabs']+m['unselected_formal_grabs']+m['terminal_retrieves']
            and all(type(v) is int and 0<=v<m['grabs_total'] for v in grabs) and
            all(b>a for a,b in zip(grabs,grabs[1:])))
        checks['admission']=bool(n and all(b>a for a,b in zip(slots,slots[1:])) and
            m['missed_target_slots']==slots[-1]+1-n and all(type(s) is int and 0<=s<300 for s in slots) and
            all(start<=r['grab_completed_ns']<=r['admitted_ns']==r['read_completed_ns']<deadline and
                r['admitted_ns']<=r['submitted_ns'] and r['grab_completed_ns']>=start+r['target_slot']*200_000_000 and
                r['completed_after_formal_end']==(r['submitted_ns']>deadline) for r in rows))
        checks['coverage_60']=bool(n and report['thread_exited'] is True and report['stop_reason']=='duration_complete'
            and report['video_loop_ended_ns']>=deadline and elapsed==60 and
            start<=report['first_admitted_ns']==rows[0]['admitted_ns']<=start+250_000_000 and
            deadline-250_000_000<=report['last_admitted_ns']==rows[-1]['admitted_ns']<deadline and
            report['first_submitted_ns']==rows[0]['submitted_ns'] and report['last_submitted_ns']==rows[-1]['submitted_ns'])
    except Exception as exc:result['error']=result['error'] or dict(type=type(exc).__name__,message=str(exc))
    return result


def assess_concurrent(directory,inherited,owner,*,inputs_unchanged,wrapper_error=None):
    s=inherited.get('summary') or {};video=owner.get('video') or {};cleanup=owner.get('video_cleanup') or {}
    h=heart_audit(directory,s);v=video_audit(directory,video,(s.get('startup') or {}).get('started_ns'))
    vc=assess_pack(video)
    vc['full_duration']=bool(video.get('requested_formal_seconds')==60 and video.get('stop_reason')=='duration_complete'
        and (video.get('metrics') or {}).get('formal_elapsed_seconds')==60)
    ipc=s.get('isolation') or {};pre=s.get('preflight') or {};checks=dict(
        inherited_pilot=inherited.get('candidate_static_pilot_completed') is True and bool(inherited.get('checks'))
            and all(inherited['checks'].values()),
        raw_journal=all(h['checks'].values()),video_journal=all(v['checks'].values()),video_checks=all(vc.values()),
        full_duration=s.get('elapsed_seconds',0)>=60 and s.get('duration_seconds')==60 and
            s.get('stop_reason')=='duration_complete' and s.get('state')=='stopped',
        effective25=(s.get('raw_hz'),s.get('processing_hz'),s.get('adc_hz'),s.get('fifo_sample_average'))==(25,25,50,2),
        original_gates=bool((s.get('audit25') or {}).get('gates')) and all(s['audit25']['gates'].values()),
        original_errors_zero=all(s.get(k)==0 for k in ('sensor_errors','pl_fifo_errors','max30102_overflow_events',
            'max30102_overflow_count','timestamp_errors','timestamp_rejected_samples','acceleration_invalid_events')),
        no_queue_full=s.get('queue_full')==dict(raw=0,processing=0,results=0) and s.get('queues_drained') is True,
        known_consumption=s.get('consumed_ppg_unknown') is False,
        real_backend=s.get('board_tested') is True and s.get('backend_source')=='pl_mmio',
        isolation=ipc.get('completed_steps')==ipc.get('pl_requests')==s.get('read',-1) and ipc.get('exitcode')==0
            and ipc.get('forced_termination') is False and ipc.get('worker_hardware_imported') is False and ipc.get('cleanup_complete') is True,
        binding=owner.get('binding_installed') is True and owner.get('prepare_calls')==1 and
            pre.get('video_shares_existing_owner') is True and pre.get('concurrent_video_target_fps')==5,
        bit_identity=pre.get('bit_sha256')==PAIR_HASHES['heart_v3b25.bit'] and pre.get('hwh_sha256')==PAIR_HASHES['heart_v3b25.hwh'],
        shared_cleanup=owner.get('video_thread_joined') is True and owner.get('actual_lease_released') is True
            and owner.get('retention_reasons')==[] and owner.get('inherited_cleanup_complete') is True
            and s.get('cleanup_complete') is True and cleanup.get('cleanup_complete') is True,
        no_fault=bool(s) and s.get('fault') is None and inherited.get('wrapper_error') is None and
            owner.get('wrapper_error') is None and wrapper_error is None,
        inputs_unchanged=inputs_unchanged is True and owner.get('inputs_unchanged') is True,
        target_5fps=video.get('target_5fps_observed') is True)
    return dict(schema='v3b25_concurrent5_trial_v1',**FLAGS,joint_60s_pilot_completed=all(checks.values()),checks=checks,
        heart_journal_audit=h,video_journal_audit=v,video_checks=vc,screen_dynamic_observed=None,
        target_5fps_observed=video.get('target_5fps_observed',False),target_15fps_observed=video.get('target_15fps_observed',False),
        wrapper_error=wrapper_error,scope_cn='受控25/25Hz心率与5fps视频共同60秒小试；2/N图像抽验；不是严格实时、准确率、15fps、DDR或完整V3B验收。')
