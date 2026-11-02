"""Independent single-SAMPLE GIL candidate on the original hybrid integration."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
if not __package__:sys.path.insert(0,str(ROOT))
if __package__:
    from .run_main_spatial_copy import verify_package as verify_base
    from .spatial_camera_guard import notebook_identity
else:
    from run_main_spatial_copy import verify_package as verify_base
    from spatial_camera_guard import notebook_identity

MANIFEST='gil-joint-manifest.json'
BOOK='GilJoint25.ipynb'
ADDED={'spatial_gil_candidate.py','spatial_gil_worker.py','run_gil_joint.py','README_GIL_JOINT.md'}
CANDIDATE_SHA='9b88e5c4bba6b94b33b3040abf0df9478254abc6c4cfb9e10b647da2e8ed865a'
PRODUCTION_SHA='faa44cdaee9ad8ee505a93049be033df530f80b68fba6af3de13ffab988c7696'
REPLAY_SHA='7336b937723bb43ef95fd528b691b05b456c2ca4221987fc36303fad1975d389'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def verify_package(root,expected=None):
    root=Path(root).resolve();checked=verify_base(root,expected);path=root/MANIFEST
    doc=json.loads(path.read_bytes())
    if (doc.get('schema')!='single_sample_gil_joint_delivery_v1' or set(doc.get('files',{}))!=ADDED
        or doc.get('base_copy_manifest_sha256')!=checked['copy_manifest_sha256']
        or doc.get('files',{}).get('spatial_gil_candidate.py')!=CANDIDATE_SHA
        or doc.get('physical_replay_result_sha256')!=REPLAY_SHA
        or doc.get('rates')!=[25,25,5] or doc.get('grid')!=[4,3]
        or doc.get('automatic_retry') is not False or doc.get('original_ps_target_retained') is not True):
        raise ValueError('joint GIL scope differs')
    for name,pin in doc['files'].items():
        member=root/name
        if member.is_symlink() or not member.resolve(strict=True).is_relative_to(root):raise ValueError('escaped GIL member')
        if sha(member)!=pin:raise ValueError('joint GIL member differs: '+name)
    if notebook_identity(root/BOOK)!=doc.get('notebook_identity_sha256'):raise ValueError('joint GIL Notebook source differs')
    if sha(root/'main_native_build/libmain_heart_readback.so')!=PRODUCTION_SHA:raise ValueError('production native binary differs')
    return dict(checked,gil_policy='hold_gil_single_sample_v1',rates=[25,25,5],grid=[4,3],
        gil_manifest_sha256=sha(path),hardware_accessed=False)


@contextmanager
def delegate(*,owner=False):
    if __package__:
        from . import run_main_spatial_copy as original,main_spatial_worker
        from .spatial_gil_worker import start_owner
        from .joint_startup import replace_attribute
    else:
        import run_main_spatial_copy as original,main_spatial_worker
        from spatial_gil_worker import start_owner
        from joint_startup import replace_attribute
    with replace_attribute(original,'ROOT',ROOT),replace_attribute(original,'verify_package',verify_package):
        if owner:
            with replace_attribute(main_spatial_worker,'start_owner',start_owner):yield original
        else:yield original


def short():
    verify_package(ROOT)
    with delegate() as original:return original.short()


def prepare():
    verify_package(ROOT)
    with delegate() as original:return original.prepare()


def run(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-GIL-JOINT25':raise ValueError('explicit RUN-GIL-JOINT25 required')
    checked=verify_package(ROOT)
    write_new(ROOT/'gil-joint-attempt.json',dict(checked=checked,automatic_retry=False,original_protections_retained=True))
    result=failure=None
    try:
        with delegate(owner=True) as original:result=original.run(hardware=True,confirmation='RUN-MAIN-SPATIAL-COPY25')
    except BaseException as exc:failure=exc
    proof=None;proof_path=ROOT/'continuous-results/gil-policy-owner.json'
    if result is not None and proof_path.is_file():proof=json.loads(proof_path.read_bytes())
    bindings=(proof or {}).get('bindings',[])
    observed=bool(proof and not proof['original_error'] and not proof['identity_error'] and len(bindings)==1
        and bindings[0].get('policy')=='hold_gil_single_sample_v1'
        and bindings[0].get('original_address')==bindings[0].get('candidate_address')
        and bindings[0].get('only_changed_symbol')=='hm_transact_sample')
    final=dict(schema='single_sample_gil_joint_result_v1',checked=checked,result=result,
        gil_policy_observed=observed,owner_policy=proof,
        original_error=dict(type=type(failure).__name__,message=str(failure)) if failure else None,
        strict_realtime_verified=False,full_v3b_acceptance_passed=False)
    try:
        write_new(ROOT/'gil-joint-final.json',final)
        with ZipFile(ROOT/'gil-joint-results.zip','x',compression=ZIP_DEFLATED) as z:
            for name in (MANIFEST,'gil-joint-attempt.json','gil-joint-final.json','main-spatial-copy-results.zip'):
                if (ROOT/name).is_file():z.write(ROOT/name,name)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    if failure is not None:raise failure
    print('结果：gil-joint-results.zip；原保护不变，失败保留、不自动重试。',flush=True)
    return final


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--check-bundle',action='store_true');m.add_argument('--short',action='store_true');a=p.parse_args()
    if a.check_bundle:print(json.dumps(verify_package(ROOT),ensure_ascii=False))
    else:raise SystemExit(0 if short()['passed'] else 1)
