"""Cold, complete-content verification; no hardware imports."""
import hashlib
import json
from pathlib import Path,PurePosixPath
import sys

MANIFEST='evidence-reuse60-manifest.json'
BOOK='EvidenceReuse60.ipynb'
SOURCE_SHA='50b823cc954051ff5a1975ec0ecfb423792a8e57300db804e77f00a7aa652fd2'
AB_SHA='1f1244a324dd78b1cf5ba18d597800961ea64f96fad570526cbb64729bb70e84'
ADDED={'evidence_reuse.py','evidence_reuse_runtime.py','evidence_reuse_guard.py',
       'run_evidence_reuse60.py','ps_early_start.py',BOOK,'README_EVIDENCE_REUSE60.md'}
POLICY=dict(rates=[25,25,5],formal_seconds=60,startup_timeout_seconds=180,ready_seconds=60,
    warmup_slots=700,ps_close_seconds=1,ce_error_limit_ns=80000000,pl_watchdog_ns=20000000,
    sample_software_ns=40000000,automatic_retry=False,algorithm_changed=False,hardware_changed=False,
    raw_and_processing_states_independent=True,immutable_input_preparation_reused=True,
    fifo_diagnostic_observer_active=False,startup_exact_bytes_digest_retained=True,
    ps_exact_bytes_validation_prefix=True,ps_nested_ab_result_reused=True,
    ps_prewarm_before_video=True,one_original_ps_bridge=True,original_hardware_order_retained=True)

def verify(root,expected_manifest_sha256=None):
    root=Path(root).resolve(strict=True);manifest=root/MANIFEST
    if manifest.is_symlink():raise ValueError('reuse manifest linked')
    raw=manifest.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if expected_manifest_sha256 is not None and digest!=expected_manifest_sha256:
        raise ValueError('reuse manifest differs')
    d=json.loads(raw)
    if (d.get('schema')!='immutable_evidence_reuse60_v1' or d.get('policy')!=POLICY
            or d.get('source_manifest_sha256')!=SOURCE_SHA or d.get('expected_members')!=473):
        raise ValueError('reuse candidate scope differs')
    from startup_digest_guard import verify as original,MANIFEST as ORIGINAL_MANIFEST,notebook_identity
    checked=original(root,SOURCE_SHA)
    verified_ab=checked['source']['source_manifest_sha256']
    if verified_ab!=AB_SHA:raise ValueError('nested AB verification identity differs')
    source=json.loads((root/ORIGINAL_MANIFEST).read_bytes());files=d.get('files',{})
    if len(files)!=472 or set(files)!=set(source['files'])|{ORIGINAL_MANIFEST}|ADDED:
        raise ValueError('reuse candidate members differ')
    for name,pin in files.items():
        if name in source['files']:
            if pin!=source['files'][name]:raise ValueError('retained member pin differs')
            continue
        if name==ORIGINAL_MANIFEST:
            if pin!={'kind':'bytes','sha256':SOURCE_SHA}:raise ValueError('retained manifest pin differs')
            continue
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:
            raise ValueError('reuse path escapes')
        path=root/name
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):raise ValueError('reuse linked member')
        kind='notebook_identity' if name==BOOK else 'bytes'
        actual=notebook_identity(path) if name==BOOK else hashlib.sha256(path.read_bytes()).hexdigest()
        if pin!={'kind':kind,'sha256':actual}:raise ValueError('reuse member differs: '+name)
    for name in ('evidence_reuse','evidence_reuse_runtime','evidence_reuse_guard','run_evidence_reuse60','ps_early_start'):
        m=sys.modules.get(name)
        if m is not None and Path(m.__file__).resolve()!=root/(name+'.py'):
            raise ValueError('mixed reuse module: '+name)
    return dict(bundle_validated=True,hardware_accessed=False,manifest_sha256=digest,
        verified_ab_manifest_sha256=verified_ab,
        source_members_unchanged=465,package_members=473,source=checked,policy=POLICY,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
