"""Standard-library-only identity for the additive five-second observer."""
import hashlib
import importlib.util
import json
from pathlib import Path,PurePosixPath
import sys

SOURCE_ZIP_SHA='c8015c168ba2621a39142b79de0753159e7c3777334b2ac6a7d8a5762a624451'
SOURCE_MAP_SHA='c24122332db99b0a364c5ecabf0d990ae245ae23b0a280f7fea52db59aac52f8'
AB_SHA='1f1244a324dd78b1cf5ba18d597800961ea64f96fad570526cbb64729bb70e84'
BOOK='FifoTiming5.ipynb';MANIFEST='fifo-time5-manifest.json'
ADDED={'fifo_time_observer.py','fifo_time_runtime.py','fifo_time_guard.py','run_fifo_time5.py',BOOK,'README_FIFO_TIMING5.md'}
POLICY=dict(formal_cap_seconds=5,rates=[25,25,5],trace_capacity=8192,additional_iic_transactions=0,
    ce_error_limit_ns=80_000_000,ce_policy_unchanged=True,raw_fields_unchanged=True,
    startup_timeout_seconds=180,warmup_slots=700,ps_close_seconds=1,automatic_retry=False,
    changes='original_call_wall_thread_cpu_observation_and_five_second_formal_cap_only')


def sha(data):return hashlib.sha256(data).hexdigest()


def notebook_identity(path):
    n=json.loads(Path(path).read_text('utf-8'));k=n['metadata']['kernelspec']
    return sha(json.dumps([n['nbformat'],k['name'],k['language'],[(c['cell_type'],''.join(c['source'])) for c in n['cells']]],
        ensure_ascii=False,separators=(',',':')).encode())


def verify(root,expected_manifest_sha256=None):
    root=Path(root).resolve(strict=True);p=root/MANIFEST
    if p.is_symlink():raise ValueError('observer manifest linked')
    raw=p.read_bytes();digest=sha(raw)
    if expected_manifest_sha256 is not None and digest!=expected_manifest_sha256:raise ValueError('FIFO observer manifest differs')
    d=json.loads(raw);source=d.get('source_members',{})
    if (d.get('schema')!='fifo_original_call_timing5_v1' or d.get('policy')!=POLICY or d.get('source_zip_sha256')!=SOURCE_ZIP_SHA
        or d.get('source_ab_manifest_sha256')!=AB_SHA or len(source)!=451
        or sha(json.dumps(source,sort_keys=True,separators=(',',':')).encode())!=SOURCE_MAP_SHA):raise ValueError('observer source/policy differs')
    files=d.get('files',{})
    if len(files)!=457 or set(files)!=set(source)|ADDED:raise ValueError('observer member set differs')
    for name,pin in files.items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:raise ValueError('observer member escapes')
        member=root/name
        if member.is_symlink() or not member.resolve(strict=True).is_relative_to(root):raise ValueError('observer member linked')
        if name==BOOK:
            if pin.get('kind')!='notebook_identity' or notebook_identity(member)!=pin['sha256']:raise ValueError('observer Notebook differs')
        elif pin.get('kind')!='bytes' or sha(member.read_bytes())!=pin['sha256']:raise ValueError('observer member differs: '+name)
        if name in source and pin!={'kind':'bytes','sha256':source[name]}:raise ValueError('retained source pin differs')
    for name in ('fifo_time_guard','fifo_time_runtime','fifo_time_observer','run_fifo_time5'):
        m=sys.modules.get(name)
        if m is not None and Path(m.__file__).resolve()!=root/(name+'.py'):raise ValueError('mixed observer module root')
    checker=root/'status60_ab_manifest.py';spec=importlib.util.spec_from_file_location('_fifo_checked_ab_manifest',checker)
    module=importlib.util.module_from_spec(spec);exec(compile(checker.read_bytes(),str(checker),'exec'),module.__dict__)
    original=module.verify_ab_package(root,AB_SHA)
    return dict(bundle_validated=True,hardware_accessed=False,manifest_sha256=digest,
        source_manifest_sha256=original['manifest_sha256'],source_members_unchanged=451,package_members=458,policy=POLICY,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
