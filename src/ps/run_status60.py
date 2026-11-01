"""Manual sixty-second joint trial; retains all SAMPLE40 baseline files."""
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
    from .run_status5 import verify_package as verify_base,write_new
    from .spatial_camera_guard import notebook_identity
else:
    from run_status5 import verify_package as verify_base,write_new
    from spatial_camera_guard import notebook_identity

MANIFEST='status60-manifest.json'
BOOK='StatusJoint60.ipynb'
ADDED={'run_status60.py','status60_runtime.py','README_STATUS60.md'}


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_package(root,expected=None):
    root=Path(root).resolve();checked=verify_base(root,expected)
    doc=json.loads((root/MANIFEST).read_bytes())
    if (doc.get('schema')!='actual_joint_status60_delivery_v1' or set(doc.get('files',{}))!=ADDED
        or doc.get('base_status5_manifest_sha256')!=checked['status5_manifest_sha256']
        or doc.get('formal_observation_seconds')!=60 or doc.get('trace_capacity')!=65536
        or doc.get('rates')!=[25,25,5] or doc.get('pl_transaction_seconds')!=.020
        or doc.get('other_protections_unchanged') is not True or doc.get('automatic_retry') is not False):
        raise ValueError('status60 scope differs')
    for name,pin in doc['files'].items():
        path=root/name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root) or sha(path)!=pin:
            raise ValueError('status60 member differs: '+name)
    if notebook_identity(root/BOOK)!=doc.get('notebook_identity_sha256'):
        raise ValueError('status60 Notebook source differs')
    return dict(checked,status60_manifest_sha256=sha(root/MANIFEST),formal_observation_seconds=60,
        trace_capacity=65536,pl_transaction_seconds=.020,hardware_started=False,
        status60_live_verified=False)


@contextmanager
def delegate(*,owner=False):
    if __package__:
        from . import run_sample40 as original,sample40_runtime
        from .status60_runtime import start_owner
        from .joint_startup import replace_attribute
    else:
        import run_sample40 as original,sample40_runtime
        from status60_runtime import start_owner
        from joint_startup import replace_attribute
    with replace_attribute(original,'ROOT',ROOT),replace_attribute(original,'verify_package',verify_package):
        if owner:
            with replace_attribute(sample40_runtime,'start_owner',start_owner):yield original
        else:yield original


def short():
    verify_package(ROOT)
    with delegate() as original:return original.short()


def prepare():
    verify_package(ROOT)
    with delegate() as original:return original.prepare()


def run(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-STATUS-JOINT60':raise ValueError('explicit RUN-STATUS-JOINT60 required')
    checked=verify_package(ROOT)
    write_new(ROOT/'status60-attempt.json',dict(checked=checked,automatic_retry=False,
        formal_observation_seconds=60,manual_hardware_confirmation=True))
    result=failure=None
    print('60秒联合试验：预热另计，正式60秒后按原流程停止；原故障可提前停止，退出问题仍如实保留。',flush=True)
    try:
        with delegate(owner=True) as original:result=original.run(hardware=True,confirmation='RUN-SAMPLE40-JOINT25')
    except BaseException as exc:failure=exc
    final=dict(schema='actual_joint_status60_result_v1',checked=checked,result=result,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False,
        scope='60-second concurrent trial; original faults and PS exit policy retained; no full V3B acceptance promotion')
    try:
        write_new(ROOT/'status60-final.json',final)
        with ZipFile(ROOT/'status60-results.zip','x',compression=ZIP_DEFLATED) as z:
            for name in (MANIFEST,'status60-attempt.json','status60-final.json','sample40-results.zip'):
                if (ROOT/name).is_file():z.write(ROOT/name,name)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    if failure is not None:raise failure
    print('结果：status60-results.zip；首错保留，不自动重试。',flush=True)
    return final


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-bundle',action='store_true');mode.add_argument('--short',action='store_true')
    args=parser.parse_args()
    if args.check_bundle:print(json.dumps(verify_package(ROOT),ensure_ascii=False))
    else:raise SystemExit(0 if short()['passed'] else 1)
