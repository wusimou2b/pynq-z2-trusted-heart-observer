"""Cold standard-library-only AB identity. Never imports files being checked."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

MANIFEST='status60-ab-manifest.json'
BOOK='StatusJoint60AB.ipynb'
BASE_ZIP_SHA='883b8993d312dd772a8d520135cfd8954eb1a0db045b0b6131b82d316eabc09c'
BASE_MAP_SHA='7b918e137763bd075aba6b0f6260edf7341540bfd9d97a1f38747a33d48c30c2'
ADDED={'status60_ab_patch.py','status60_ab_runtime.py','status60_ab_manifest.py',
       'run_status60_ab.py',BOOK,'README_STATUS60_AB.md'}
POLICY=dict(pairing_policy_version='a3r_causal_reuse80_v1',clock_policy_version='ce_fifo_count_host80_v1',
    period_ns=40_000_000,pair_age_ns=80_000_000,count_error_ns=80_000_000,
    host_limit_ns=500_000_000,window_ns=2_000_000_000,anchors=128,audit_capacity=4096,
    formal_seconds=60,rates=[25,25,5],sample_seconds=.040,main_init_stop_seconds=.020,
    rtl_watchdog_seconds=.020,ps_close_seconds=1,raw_gap_policy_changed=True,
    historical_imu_read_reuse_enabled=True,base_algorithm_thresholds_unchanged=True,
    physical_sample_completeness_verified=False,automatic_retry=False,
    runtime_path='main_spatial_owner_sample_v1')


def sha_bytes(data):return hashlib.sha256(data).hexdigest()


def notebook_identity(path):
    nb=json.loads(Path(path).read_text('utf-8'));kernel=nb['metadata']['kernelspec']
    data=[nb['nbformat'],kernel['name'],kernel['language'],
          [(c['cell_type'],''.join(c['source'])) for c in nb['cells']]]
    return sha_bytes(json.dumps(data,ensure_ascii=False,separators=(',',':')).encode())


def local(root,name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name:
        raise ValueError('invalid AB member path')
    p=PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:raise ValueError('AB member escapes root')
    target=root/name
    if target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):
        raise ValueError('AB member is linked or outside root')
    return target


def verify_ab_package(root,expected_manifest_sha256=None):
    root=Path(root).resolve(strict=True);data=(root/MANIFEST).read_bytes();digest=sha_bytes(data)
    if expected_manifest_sha256 is not None and digest!=expected_manifest_sha256:
        raise ValueError('AB manifest digest differs')
    d=json.loads(data)
    if (d.get('schema')!='status60_a3r_ce_delivery_v1' or d.get('policy')!=POLICY
        or d.get('baseline_zip_sha256')!=BASE_ZIP_SHA
        or d.get('live25_acceptance_passed') is not False or d.get('full_v3b_acceptance_passed') is not False):
        raise ValueError('AB manifest scope differs')
    baseline=d.get('baseline_files',{})
    if len(baseline)!=444 or sha_bytes(json.dumps(baseline,sort_keys=True,separators=(',',':')).encode())!=BASE_MAP_SHA:
        raise ValueError('AB baseline member map differs')
    files=d.get('files',{})
    if set(files)!=set(baseline)|ADDED or len(files)!=450:raise ValueError('AB release member set differs')
    for name,record in files.items():
        path=local(root,name)
        if name==BOOK:
            if record.get('kind')!='notebook_identity' or notebook_identity(path)!=record.get('sha256'):
                raise ValueError('AB Notebook source differs')
        else:
            if record.get('kind')!='bytes' or sha_bytes(path.read_bytes())!=record.get('sha256'):
                raise ValueError('AB member differs: '+name)
        if name in baseline and record!={'kind':'bytes','sha256':baseline[name]}:
            raise ValueError('AB baseline pin changed')
    for name in ['status60_ab_manifest','status60_ab_runtime','run_status60_ab','status60_ab_patch']:
        module=sys.modules.get(name)
        if module is not None and Path(module.__file__).resolve()!=root/(name+'.py'):
            raise ValueError('mixed AB module root: '+name)
    return dict(bundle_validated=True,hardware_accessed=False,manifest_sha256=digest,
        baseline_files_verified=444,package_members=451,policy=POLICY,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)


def validate_epoch(epoch):
    if not isinstance(epoch,str) or len(epoch)!=32 or any(c not in '0123456789abcdef' for c in epoch):
        raise ValueError('AB run epoch differs')
