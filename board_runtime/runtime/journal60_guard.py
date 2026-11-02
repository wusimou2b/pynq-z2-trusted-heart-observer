"""Pure-file identity and saved-ARM timing gate for the journal60 candidate."""
import hashlib
import json
import math
from pathlib import Path,PurePosixPath
import sys

SOURCE_SHA='cacaa57d65e6713ece0426afad549b91647609fe8d316a0a2b692dc014ee8cc6'
INPUT_SHA='e0fe69ebffe25d62b5409aeadce88ff1294c6ec9bd86cd89e570f5216c2483fd'
MANIFEST='journal60-manifest.json';BOOK='Journal60.ipynb'
ADDED={'native40_boundary.py','heart_video_journal.py','journal60_guard.py','journal60_runtime.py',
    'run_journal60.py',BOOK,'README_JOURNAL60.md','journal60-arm-evidence.json','journal60-scalar-evidence.json'}
POLICY=dict(rates=[25,25,5],formal_seconds=60,native_deadline_seconds=.040,software_step_seconds=1,
    python_return40_is_warning=True,rtl_seconds=.020,init_stop_seconds=.020,ps_close_seconds=1,
    freshness_ns=1000000000,display_age_ns=100000000,display_lock_seconds=.05,
    ready_seconds=60,startup_seconds=180,warmup_slots=700,owner_switch_seconds=.001,
    ps_switch_unchanged=True,gc_changed=False,algorithm_changed=False,hardware_changed=False,
    ipc_protocol_changed=False,scalar_journal_conversion=True,automatic_retry=False)

def verify_timing(root):
    root=Path(root);d=json.loads((root/'journal60-arm-evidence.json').read_bytes())
    if (d.get('schema')!='saved925_journal_owner_abba_v1' or d.get('complete') is not True
        or d.get('candidate_timing_passed') is not True or d.get('hardware_accessed') is not False
        or d.get('camera_started') is not False or d.get('policy_restored') is not True
        or d.get('fault') is not None or d.get('input_sha256')!=INPUT_SHA or d.get('source_manifest_sha256')!=SOURCE_SHA):
        raise ValueError('journal60 ARM evidence is not complete/passing')
    blocks=d.get('blocks',[])
    if (len(blocks)!=4 or [b.get('optimized') for b in blocks]!=[False,True,True,False]
        or d.get('independent_owner_per_group') is not True or len({b.get('owner_pid') for b in blocks})!=4):
        raise ValueError('journal60 ARM ABBA groups differ')
    for b in blocks:
        if b.get('count')!=925 or b.get('comparison_differences')!=0:raise ValueError('journal60 replay fields differ')
        if b['optimized'] and (b['mean_effective_ms']>32 or b['worst10_ms']>400
            or not all(math.isfinite(b[k]) and b[k]>=0 for k in ('mean_effective_ms','worst10_ms'))
            or b['display_reader_loops']<=0 or b['display_stale_views'] or b['display_reader_errors']
            or b['reader_exitcode']!=0 or b.get('journal_counts',{}).get('results_saved')!=925):raise ValueError('journal60 timing target not achieved')
        if b['optimized']:
            ps=b.get('ps_final',{})
            if (ps.get('arm_native') is not True or ps.get('cleanup_complete') is not True
                or ps.get('forced_termination') is not False or ps.get('exitcode')!=0
                or ps.get('warmup_slots')!=700):raise ValueError('journal60 original ARM/exit boundary not verified')
    expected=hashlib.sha256((root/'heart_video_journal.py').read_bytes()).hexdigest()
    if d.get('probe_source_sha256',{}).get('heart_video_journal')!=expected:
        raise ValueError('journal60 measured scalar converter differs')
    scalar=json.loads((root/'journal60-scalar-evidence.json').read_bytes())
    if (scalar.get('schema')!='saved925_scalar_journal_abba_v1' or scalar.get('input_sha256')!=INPUT_SHA
        or scalar.get('source_manifest_sha256')!=SOURCE_SHA or scalar.get('hardware_accessed') is not False
        or scalar.get('camera_started') is not False or scalar.get('gc_unchanged') is not True
        or scalar.get('scalar_fields_equal') is not True or scalar.get('csv_bytes_equal') is not True
        or scalar.get('source_sha256',{}).get('heart_video_journal')!=expected):raise ValueError('journal scalar byte evidence differs')
    rows=scalar.get('blocks',[])
    if len(rows)!=4 or [r.get('optimized') for r in rows]!=[False,True,True,False] or any(r.get('count')!=925 for r in rows):
        raise ValueError('journal scalar groups differ')
    if len({r['csv_sha256'] for r in rows})!=1:raise ValueError('journal CSV bytes differ')
    means={x:sum(r['cpu_ms_per_row'] for r in rows if r['optimized']==x)/2 for x in (False,True)}
    if not all(math.isfinite(v) and v>0 for v in means.values()) or means[True]>=means[False]:raise ValueError('journal CPU gain not demonstrated')
    return dict(passed=True,journal_cpu_ms=means,scope='saved925 original IPC/display/result-CSV simulation, not physical PL/IIC/video acceptance')

def verify(root,expected_manifest_sha256=None):
    root=Path(root).resolve(strict=True);path=root/MANIFEST
    if path.is_symlink():raise ValueError('journal60 manifest linked')
    raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();d=json.loads(raw)
    if expected_manifest_sha256 is not None and sha!=expected_manifest_sha256:raise ValueError('journal60 manifest differs')
    if d.get('schema')!='owner_journal60_v1' or d.get('policy')!=POLICY or d.get('source_manifest_sha256')!=SOURCE_SHA or d.get('expected_members')!=491:
        raise ValueError('journal60 scope differs')
    from owner_schedule_guard import verify as original,MANIFEST as SOURCE_MANIFEST
    from startup_digest_guard import notebook_identity
    old=original(root,SOURCE_SHA);pins=json.loads((root/SOURCE_MANIFEST).read_bytes())['files'];files=d['files']
    if len(files)!=490 or set(files)!=set(pins)|{SOURCE_MANIFEST}|ADDED:raise ValueError('journal60 members differ')
    for name,pin in files.items():
        if name in pins:
            if pin!=pins[name]:raise ValueError('journal60 retained member pin differs')
            continue
        if name==SOURCE_MANIFEST:
            if pin!={'kind':'bytes','sha256':SOURCE_SHA}:raise ValueError('journal60 source manifest differs')
            continue
        p=PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name:raise ValueError('journal60 path escapes')
        target=root/name
        if target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):raise ValueError('journal60 linked member')
        kind='notebook_identity' if name==BOOK else 'bytes'
        value=notebook_identity(target) if name==BOOK else hashlib.sha256(target.read_bytes()).hexdigest()
        if pin!={'kind':kind,'sha256':value}:raise ValueError('journal60 content differs: '+name)
    for name in ('native40_boundary','heart_video_journal','journal60_guard','journal60_runtime','run_journal60'):
        m=sys.modules.get(name)
        if m is not None and Path(m.__file__).resolve()!=root/(name+'.py'):raise ValueError('mixed journal60 module: '+name)
    timing=verify_timing(root)
    return dict(bundle_validated=True,hardware_accessed=False,manifest_sha256=sha,policy=POLICY,
        source_manifest_sha256=SOURCE_SHA,source_members_unchanged=481,package_members=491,
        timing=timing,source=old,live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
