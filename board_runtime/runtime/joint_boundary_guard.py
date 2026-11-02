"""Cold identity and interval audit. Data only; never loads archived code."""
import csv
from collections import defaultdict
import json
from pathlib import Path
import statistics

if __package__:
    from .joint_overlap_guard import verify_overlap,sha,write_new,notebook_code_hash,FLAGS
    from .joint_boundary import CAPACITIES,FIELDS
else:
    from joint_overlap_guard import verify_overlap,sha,write_new,notebook_code_hash,FLAGS
    from joint_boundary import CAPACITIES,FIELDS

MANIFEST='joint-boundary-manifest.json';NOTEBOOK='JointBoundary5.ipynb'
EXTRAS={'joint_boundary.py','joint_boundary_worker.py','joint_boundary_guard.py','run_joint_boundary.py','README_BOUNDARY5.md'}
BASE_SHA='8a8fc4aa5f0f94c43f671296b6a2583a9340f9fa09ae99e4322934ef7a353a89'

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def verify_boundary(root):
    root=Path(root);base=verify_overlap(root);doc=read(root/MANIFEST)
    if (sha(root/'joint-overlap-manifest.json')!=BASE_SHA or doc.get('base_manifest_sha256')!=BASE_SHA or
        doc.get('schema')!='v3b25_boundary5_package_v1' or set(doc.get('files',{}))!=EXTRAS or
        tuple(doc.get(k) for k in ('raw_hz','processing_hz','video_target_fps','formal_seconds','warmup_slots','startup_timeout_seconds'))!=(25,25,5,60,700,90) or
        doc.get('capacities')!=CAPACITIES or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('boundary scope changed')
    for name,h in doc['files'].items():
        path=root/name
        if path.is_symlink() or not path.is_file() or sha(path)!=h:raise ValueError('boundary source changed: '+name)
    if notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):raise ValueError('boundary Notebook code changed')
    return dict(base,boundary_manifest_sha256=sha(root/MANIFEST),boundary_observation_complete=False)

def union_ns(intervals):
    total=0;end=None
    for a,b in sorted(intervals):
        if b<a:raise ValueError('negative interval')
        if end is None or a>end:total+=b-a
        else:total+=max(0,b-end)
        end=b if end is None else max(end,b)
    return total

def validate_ledger(doc):
    errors=[]
    try:
        if (doc['schema']!='v3b25_owner_boundaries_v1' or doc['fields']!=list(FIELDS) or
            doc['payload_bytes']!=1933312 or doc['hooks_installed'] is not True or doc['hooks_restored'] is not True or doc.get('install_error') is not None or
            doc['clocks']!=dict(wall='monotonic_ns',cpu='thread_time_ns') or type(doc['owner_pid']) is not int or doc['owner_pid']<=0 or
            set(doc['streams'])!=set(CAPACITIES)):raise ValueError('ledger identity/scope')
        for name,s in doc['streams'].items():
            rows=s['rows']
            if (s['capacity']!=CAPACITIES[name] or s['error'] is not None or s['dropped']!=0 or
                not 0<=s['stored']==s['calls']==len(rows)<=s['capacity']):raise ValueError('stream counts/error: '+name)
            previous=None
            for i,r in enumerate(rows):
                if (len(r)!=8 or any(type(v) is not int for v in r) or r[0]!=i or r[1]<-1 or
                    not 0<=r[2]<=r[3] or not 0<=r[4]<=r[3]-r[2] or r[5]!=s['thread_id'] or r[5]<=0 or
                    r[6] not in (0,1) or r[7]<0 or previous is not None and r[2]<previous):
                    raise ValueError('stream row/clock/thread: '+name)
                previous=r[3]
    except (KeyError,TypeError,ValueError) as exc:errors.append(dict(type=type(exc).__name__,message=str(exc)))
    return dict(complete=not errors,errors=errors)

def distribution(values):
    if not values:return dict(count=0)
    v=sorted(x/1e6 for x in values);p=.99*(len(v)-1);lo=int(p);hi=min(lo+1,len(v)-1)
    return dict(count=len(v),mean_ms=statistics.mean(v),p99_ms=v[lo]+(v[hi]-v[lo])*(p-lo),maximum_ms=v[-1])

def assess_boundaries(directory,original):
    directory=Path(directory);result=dict(schema='v3b25_boundary5_trial_v1',**FLAGS,
        boundary_observation_complete=False,joint_60s_pilot_completed=original.get('joint_60s_pilot_completed') is True,
        checks={},error=None,invalid_points=[],fifo_batches=[],queue_wait_bins=[],
        scope_cn='联合边界观察，不是修复或实时/准确率/DDR验收；CPU仅调用线程，嵌套/并发不相加，时间重叠不证明因果。')
    try:
        doc=read(directory/'owner_boundaries.json');ledger=validate_ledger(doc);result['ledger']=ledger
        result['checks']['ledger']=ledger['complete'];streams=doc['streams']
        with (directory/'capture/raw.csv').open(encoding='utf-8') as f:raw=list(csv.DictReader(f))
        with (directory/'capture/results.csv').open(encoding='utf-8') as f:rows=list(csv.DictReader(f))
        summary=read(directory/'capture/summary.json');epoch=summary['startup']['started_ns'];deadline=epoch+60_000_000_000
        result.update(formal_epoch_ns=epoch,formal_deadline_ns=deadline,owner_pid=doc['owner_pid'],raw_rows=len(raw),result_rows=len(rows))
        def matched(name,token):return [r for r in streams[name]['rows'] if r[1]==token and r[6]==1]
        raw_by_seq={int(r['sequence']):r for r in raw};batches=defaultdict(list)
        for r in raw:batches[int(r['batch_id'])].append(r)
        capture_ok=True
        for batch in batches.values():
            token=int(batch[0]['sequence']);calls=matched('read_batch',token)
            if len(calls)!=1 or calls[0][7]!=len(batch) or not calls[0][2]<=int(batch[0]['ppg_read_completed_ns'])<=calls[0][3]:capture_ok=False
            if len(batch)>1:result['fifo_batches'].append(dict(first_sequence=token,size=len(batch),read_completed_ns=int(batch[0]['ppg_read_completed_ns'])))
        step_ok=True
        for row in rows:
            token=int(row['sequence']);calls=matched('step',token)
            if len(calls)!=1 or not int(row['processing_started_ns'])<=calls[0][2]<=calls[0][3]<=int(row['processing_finished_ns']):step_ok=False
            if row['slot_valid']=='False':
                r=raw_by_seq[token];end=int(r['ppg_read_completed_ns']);previous=raw_by_seq.get(token-1)
                start=int(previous['ppg_read_completed_ns']) if previous else epoch
                overlaps={}
                for name,s in streams.items():
                    spans=[(max(start,x[2]),min(end,x[3])) for x in s['rows'] if x[2]<end and x[3]>start]
                    overlaps[name]=dict(calls=len(spans),wall_union_ns=union_ns(spans))
                result['invalid_points'].append(dict(sequence=token,reason=row['slot_reason'],begin_ns=start,end_ns=end,
                    batch_id=int(r['batch_id']),fifo_batch_size=int(r['fifo_batch_size']),overlap=overlaps))
        frames=[json.loads(line) for line in (directory/'video/frames.jsonl').read_text(encoding='utf-8').splitlines()]
        video_ok=True
        for row in frames:
            token=row['source_sequence'];a=matched('frame',token);b=matched('vision',token)
            if len(a)!=1 or len(b)!=1 or not row['admitted_ns']<=a[0][2]<=b[0][2]<=b[0][3]<=a[0][3]<=row['submitted_ns']:video_ok=False
        video_report=read(directory/'video/worker_result.json');metrics=video_report['metrics']
        result['checks'].update(capture_coverage=capture_ok and len(batches)>0,processing_coverage=step_ok and len(rows)>0,
            video_coverage=video_ok and len(frames)>0,
            video_calls=(streams['grab']['calls']==metrics['grabs_total'] and streams['retrieve']['calls']==metrics['selected_grabs']+metrics['terminal_retrieves']),
            publication_calls=streams['snapshot']['calls']>=streams['publish']['calls']>0,
            owner_identity=read(directory/'owner_startup.json')['owner_pid']==doc['owner_pid'])
        result['boundaries']={}
        for name,s in streams.items():
            phase_rows=dict(preparation=[],formal=[],tail=[],straddling=[])
            for r in s['rows']:
                phase='preparation' if r[3]<epoch else 'tail' if r[2]>=deadline else 'formal' if r[2]>=epoch and r[3]<=deadline else 'straddling'
                phase_rows[phase].append(r)
            result['boundaries'][name]={phase:dict(wall=distribution([r[3]-r[2] for r in rs]),caller_thread_cpu=distribution([r[4] for r in rs])) for phase,rs in phase_rows.items()}
        bins=defaultdict(list)
        for r in rows:bins[int(float(r['time_s'])//10)].append(int(r['processing_queue_wait_ns']))
        result['queue_wait_bins']=[dict(time_start_seconds=k*10,**distribution(v)) for k,v in sorted(bins.items())]
        result['original_isolation']=summary.get('isolation');result['original_fault']=summary.get('fault')
        result['boundary_observation_complete']=all(result['checks'].values())
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc))
    return result
