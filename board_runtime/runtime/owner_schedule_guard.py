"""Owner scheduling candidate identity, validated before runtime imports."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import sys

MANIFEST='owner-schedule-manifest.json'
BOOK='OwnerSchedule60.ipynb'
SOURCE_SHA='534cbb9e2390140ba16f428703cc2756393748f376533cee14ba4404cd1576ba'
ADDED={'owner_timeslice.py','owner_schedule_guard.py','owner_schedule_runtime.py','run_owner_schedule60.py',BOOK,'README_OWNER_SCHEDULE60.md','owner_display_copy.py'}
POLICY=dict(rates=[25,25,5],formal_seconds=60,owner_switch_seconds=.001,ps_child_switch_unchanged=True,
    sample_seconds=.040,rtl_watchdog_seconds=.020,ps_close_seconds=1,ready_seconds=60,
    startup_seconds=180,warmup_slots=700,ce_error_ns=80000000,freshness_ns=1000000000,
    gc_changed=False,algorithm_changed=False,hardware_changed=False,ipc_protocol_changed=False,automatic_retry=False,display_bulk_writer=True,display_lock_seconds=.05,display_status_age_ns=100000000)

def verify(root,expected_manifest_sha256=None):
    root=Path(root).resolve(strict=True);manifest=root/MANIFEST
    if manifest.is_symlink():raise ValueError('schedule manifest linked')
    raw=manifest.read_bytes();sha=hashlib.sha256(raw).hexdigest();d=json.loads(raw)
    if expected_manifest_sha256 is not None and sha!=expected_manifest_sha256:raise ValueError('schedule manifest differs')
    if d.get('schema')!='owner_schedule60_v1' or d.get('policy')!=POLICY or d.get('source_manifest_sha256')!=SOURCE_SHA or d.get('expected_members')!=481:
        raise ValueError('schedule scope differs')
    from evidence_reuse_guard import verify as original,MANIFEST as SOURCE_MANIFEST
    from startup_digest_guard import notebook_identity
    source=original(root,SOURCE_SHA);pins=json.loads((root/SOURCE_MANIFEST).read_bytes())['files'];files=d['files']
    if len(files)!=480 or set(files)!=set(pins)|{SOURCE_MANIFEST}|ADDED:raise ValueError('schedule members differ')
    for name,pin in files.items():
        if name in pins:
            if pin!=pins[name]:raise ValueError('retained schedule member pin differs')
            continue
        if name==SOURCE_MANIFEST:
            if pin!={'kind':'bytes','sha256':SOURCE_SHA}:raise ValueError('retained source manifest pin differs')
            continue
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:raise ValueError('schedule path escapes')
        path=root/name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):raise ValueError('schedule member linked')
        kind='notebook_identity' if name==BOOK else 'bytes'
        digest=notebook_identity(path) if name==BOOK else hashlib.sha256(path.read_bytes()).hexdigest()
        if pin!={'kind':kind,'sha256':digest}:raise ValueError('schedule content differs: '+name)
    for name in ('owner_timeslice','owner_schedule_guard','owner_schedule_runtime','run_owner_schedule60','owner_display_copy'):
        m=sys.modules.get(name)
        if m is not None and Path(m.__file__).resolve()!=root/(name+'.py'):raise ValueError('mixed schedule runtime: '+name)
    return dict(bundle_validated=True,hardware_accessed=False,manifest_sha256=sha,policy=POLICY,
        source_manifest_sha256=SOURCE_SHA,source_members_unchanged=473,package_members=481,source=source,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
