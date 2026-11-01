"""Cold identity for the single-construction candidate; original gates retained."""
import json
from pathlib import Path
if __package__:
    from .joint_boundary_guard import verify_boundary,sha,write_new,notebook_code_hash,FLAGS
else:
    from joint_boundary_guard import verify_boundary,sha,write_new,notebook_code_hash,FLAGS

BASE_SHA='46aa1508543ad75e0866f90d7b98c6cfbd2ed0dfdeabfe0906c350ba080f40c1'
MANIFEST='joint-snapshot-manifest.json'
NOTEBOOK='JointSnapshot5.ipynb'
EXTRAS={'joint_snapshot.py','joint_snapshot_worker.py','joint_snapshot_guard.py','run_joint_snapshot.py','README_SNAPSHOT5.md'}
ADAPTER=dict(schema='v3b25_snapshot_adapter_v1',installed=True,restored=True,
    final_snapshot_constructions=1,original_guard_retained=True,status_cached=False)

def verify_snapshot(root):
    root=Path(root);base=verify_boundary(root)
    doc=json.loads((root/MANIFEST).read_text(encoding='utf-8'))
    if (sha(root/'joint-boundary-manifest.json')!=BASE_SHA or doc.get('base_manifest_sha256')!=BASE_SHA or
        doc.get('schema')!='v3b25_snapshot5_package_v1' or set(doc.get('files',{}))!=EXTRAS or
        tuple(doc.get(k) for k in ('raw_hz','processing_hz','video_target_fps','formal_seconds','warmup_slots','startup_timeout_seconds'))!=(25,25,5,60,700,90) or
        doc.get('optimization')!='one_final_snapshot_original_guard' or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('snapshot scope changed')
    for name,h in doc['files'].items():
        path=root/name
        if path.is_symlink() or not path.is_file() or sha(path)!=h:raise ValueError('snapshot source changed: '+name)
    if notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):raise ValueError('snapshot Notebook code changed')
    return dict(base,snapshot_manifest_sha256=sha(root/MANIFEST),snapshot_candidate_completed=False)

def assess_snapshot(directory,original):
    result=dict(schema='v3b25_snapshot5_trial_v1',snapshot_candidate_completed=False,**FLAGS,
        joint_60s_pilot_completed=original.get('joint_60s_pilot_completed') is True,
        boundary_observation_complete=original.get('boundary_observation_complete') is True,
        optimization_lifecycle_verified=False,error=None,
        scope_cn='仅状态快照构造减负；原guard/25,25Hz/5fps/GC/保护不变。不是严格实时、准确率或DDR验收。')
    try:
        doc=json.loads((Path(directory)/'owner_boundaries.json').read_text(encoding='utf-8'))
        result['adapter']=doc['snapshot_optimization']
        result['optimization_lifecycle_verified']=result['adapter']==ADAPTER
        result['snapshot_candidate_completed']=bool(result['optimization_lifecycle_verified'] and
            result['boundary_observation_complete'] and result['joint_60s_pilot_completed'] and original.get('wrapper_error') is None)
    except Exception as exc:result['error']=dict(type=type(exc).__name__,message=str(exc))
    return result
