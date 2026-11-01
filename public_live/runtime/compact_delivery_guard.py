"""Additive candidate identity: retained502-member package stays byte-for-byte intact."""
import hashlib,importlib.util,json,sys
from pathlib import Path,PurePosixPath

BASE_SHA='a9ff499064a79b7ae7eddf6b30cee172ac1b285c66dde1876357229197712fea'
MANIFEST='compact-delivery-manifest.json'
BOOK='CompactJoint25.ipynb'
POLICY=dict(raw_hz=25,processing_hz=25,video_fps=5,formal_seconds=60,warmup_slots=700,
    ready_seconds=60,startup_seconds=300,ps_exit_seconds=1,software_step_seconds=1,
    rtl_seconds=.020,native_sample_seconds=.040,source_age_ns=1000000000,ce_limit_ns=80000000,
    queues=[8,250,250],gc_original_window=True,curve_display='browser4',hdmi_display='video_bpm_route',
    sample_ipc='one_roundtrip_exact_refs_v1',sample_dropping=False,automatic_retry=False)
REQUIRED={'compact_delivery_guard.py','compact_delivery_runtime.py','compact_timeout_driver.py','compact_entry.py',
    'main_rpc_compact.py','main_tail_compact.py','compact_board_owner.py','compact_spatial_assessment.py','compact_context_binding.py',
    'compact_video_process.py','compact_video_runtime.py','compact_run_video_split.py',BOOK,
    'compact_hardware/timeout-release.json','compact_hardware/heart_v3b25_main.bit','compact_hardware/heart_v3b25_main.hwh',
    'compact_native/main_heart_native_build.py','compact_native/main_heart_readback.c','compact_native/main_heart_readback.py',
    'compact_native/main-native-build.json','compact_native/main_native_build/libmain_heart_readback.so',
    'compact_native/main_native_build/main_heart_readback.s','compact-evidence.json','README_COMPACT.md'}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def book_identity(path):
    b=json.loads(Path(path).read_bytes());k=b['metadata']['kernelspec']
    return hashlib.sha256(json.dumps([b['nbformat'],k['name'],k['language'],
        [(c['cell_type'],''.join(c['source'])) for c in b['cells']]],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def verify(root,expected):
    root=Path(root).resolve();path=root/MANIFEST
    if sha(path)!=expected:raise ValueError('compact candidate manifest identity differs')
    d=json.loads(path.read_bytes())
    if (d.get('schema')!='compact_joint25_candidate_v1' or d.get('baseline_sha256')!=BASE_SHA
            or d.get('policy')!=POLICY or d.get('build_complete') is not True
            or not REQUIRED<=set(d.get('added_files',{}))):
        raise ValueError('compact candidate scope differs')
    from video_split_guard import verify as baseline
    old=baseline(root,BASE_SHA)
    for name,digest in d['added_files'].items():
        p=PurePosixPath(name);target=root/name
        if p.is_absolute() or '..' in p.parts or ':' in name or '\\' in name or target.is_symlink() or not target.resolve(strict=True).is_relative_to(root):
            raise ValueError('compact member path invalid')
        actual=book_identity(target) if name==BOOK else sha(target)
        if actual!=digest:raise ValueError('compact member differs: '+name)
        if name.endswith('.py') and '/' not in name:
            loaded=sys.modules.get(name[:-3])
            if loaded is not None and Path(loaded.__file__).resolve()!=target:
                raise ValueError('mixed compact module root: '+name)
    if json.loads((root/BOOK).read_bytes())['metadata']['compact_manifest_sha256']!=expected:
        raise ValueError('compact notebook handoff identity differs')
    proof=json.loads((root/'compact-evidence.json').read_bytes())
    groups=proof['arm_ipc']['groups']
    if (proof.get('local_tests_passed') is not True or proof['arm_ipc'].get('hardware_accessed') is not False
            or [g['group'] for g in groups]!=list('ABBA') or any(g['count']!=1504 or not g['natural_exit_1s'] for g in groups)
            or len({g['frames_sha256'] for g in groups})!=1):raise ValueError('compact verification incomplete')
    return dict(bundle_validated=True,baseline_preserved=old['package_members'],manifest_sha256=expected,
        hardware_accessed=False,live25_acceptance_passed=False)

def native_module(root):
    path=Path(root)/'compact_native/main_heart_native_build.py';name='compact_native_builder'
    if name in sys.modules:
        module=sys.modules[name]
        if Path(module.__file__).resolve()!=path.resolve():raise ValueError('mixed timeout native builder')
        return module
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module);sys.modules[name]=module;return module

def verify_release(directory):
    directory=Path(directory).resolve();root=directory.parent
    doc=json.loads((directory/'timeout-release.json').read_bytes())
    if (doc.get('schema')!='timeout_safe_main_spatial_v1' or doc.get('core_version')!=0x20001
        or doc.get('watchdog_cycles')!=2000000 or doc.get('static_validation_passed') is not True
        or doc['metrics']['wns_ns']<0 or doc['metrics']['whs_ns']<0
        or doc['metrics']['drc_errors'] or doc['metrics']['drc_critical']):
        raise ValueError('timeout-safe whole-board release gate incomplete')
    if set(doc['pair'])!={'heart_v3b25_main.bit','heart_v3b25_main.hwh'}:raise ValueError('matched pair missing')
    for name,digest in doc['pair'].items():
        if sha(directory/name)!=digest:raise ValueError('timeout-safe pair differs')
    from compact_context_binding import RELEASE_PAIR
    if (doc['pair']['heart_v3b25_main.bit'],doc['pair']['heart_v3b25_main.hwh'])!=RELEASE_PAIR:
        raise ValueError('release pair differs from A3/C binding')
    native_module(root).verify_build(root/'compact_native')
    return dict(files=doc['pair'],pair_integrity_verified=True,preboard_gate_passed=True,
        hardware_accessed=False,live_25hz_passed=False,full_v3b_acceptance_passed=False)
