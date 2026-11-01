"""Whole-package validation is retained; no metadata-only identity shortcuts."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys

MANIFEST='startup-digest5-manifest.json'
BOOK='StartupDigest5.ipynb'
SOURCE_SHA='57861018e536e7fac02189fc61a26fb4577de35e149fd451451d099d96eba54d'
ADDED={'startup_digest.py','startup_digest_runtime.py','startup_digest_guard.py',
       'run_startup_digest5.py',BOOK,'README_STARTUP_DIGEST5.md'}
POLICY=dict(rates=[25,25,5],formal_seconds=5,startup_timeout_seconds=180,warmup_slots=700,
    ready_seconds=60,ps_close_seconds=1,ce_error_limit_ns=80000000,automatic_retry=False,
    algorithm_changed=False,hardware_changed=False,cache_key='exact_immutable_bytes',
    every_file_read_retained=True,cache_before_original_StartupTrace_only=True,
    max_cache_bytes=33554432,max_cache_entries=2048,min_cache_bytes=1024)


def sha(data):return hashlib.sha256(data).hexdigest()


def notebook_identity(path):
    n=json.loads(Path(path).read_text('utf-8'));k=n['metadata']['kernelspec']
    return sha(json.dumps([n['nbformat'],k['name'],k['language'],
        [(c['cell_type'],''.join(c['source'])) for c in n['cells']]],ensure_ascii=False,separators=(',',':')).encode())


def verify(root,expected_manifest_sha256=None):
    root=Path(root).resolve(strict=True)
    manifest=root/MANIFEST
    if manifest.is_symlink():raise ValueError('startup manifest linked')
    raw=manifest.read_bytes();digest=sha(raw)
    if expected_manifest_sha256 is not None and digest!=expected_manifest_sha256:
        raise ValueError('startup manifest differs')
    d=json.loads(raw)
    if (d.get('schema')!='fifo_startup_exact_bytes_v1' or d.get('policy')!=POLICY
            or d.get('source_fifo_manifest_sha256')!=SOURCE_SHA or d.get('expected_members')!=465):
        raise ValueError('startup candidate scope differs')
    from fifo_time_guard import verify as verify_original,MANIFEST as ORIGINAL_MANIFEST
    original=verify_original(root,SOURCE_SHA)
    source=json.loads((root/ORIGINAL_MANIFEST).read_bytes())
    files=d.get('files',{})
    if len(files)!=464 or set(files)!=set(source['files'])|{ORIGINAL_MANIFEST}|ADDED:
        raise ValueError('startup candidate members differ')
    for name,pin in files.items():
        # The original verifier above has just checked these complete contents,
        # paths and pins. Validate our reference map without hashing them twice
        # inside this same verification call.
        if name in source['files']:
            if pin!=source['files'][name]:raise ValueError('retained FIFO pin changed')
            continue
        if name==ORIGINAL_MANIFEST:
            if pin!={'kind':'bytes','sha256':SOURCE_SHA}:raise ValueError('retained FIFO manifest changed')
            continue
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:
            raise ValueError('startup member escapes')
        path=root/name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError('startup member linked')
        expected_kind='notebook_identity' if name==BOOK else 'bytes'
        actual=notebook_identity(path) if expected_kind=='notebook_identity' else sha(path.read_bytes())
        if pin!={'kind':expected_kind,'sha256':actual}:
            raise ValueError('startup member differs: '+name)
    for name in ('startup_digest','startup_digest_runtime','startup_digest_guard','run_startup_digest5'):
        m=sys.modules.get(name)
        if m is not None and Path(m.__file__).resolve()!=root/(name+'.py'):
            raise ValueError('mixed startup module: '+name)
    return dict(bundle_validated=True,hardware_accessed=False,manifest_sha256=digest,
        source_members_unchanged=458,package_members=465,source=original,policy=POLICY,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
