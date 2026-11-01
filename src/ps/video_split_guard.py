"""Pure-file identity for the real video process candidate."""
import hashlib
import json
import sys
from pathlib import Path,PurePosixPath
from types import FunctionType

MANIFEST='video-process-manifest.json'
SOURCE_SHA='515fb748504d1cb4dae762899f80073c62332f5551340c0671d33858a948f365'
BOOK='VideoProcess25.ipynb'
ADDED={'video_split_guard.py','video_split_state.py','video_split_process.py','video_split_resources.py',
       'video_split_runtime.py','video_split_preview.py','run_video_split.py',BOOK,'README_VIDEO_PROCESS.md','video-split-local-evidence.json'}
STARTUP_SECONDS=300
POLICY=dict(raw_hz=25,processing_hz=25,video_fps=5,formal_seconds=60,warmup_slots=700,ready_seconds=60,
    startup_seconds=STARTUP_SECONDS,ps_exit_seconds=1,frame_transfer_seconds=1,hdmi_close_seconds=3,frame_release_seconds=2,
    display_lock_seconds=.05,status_age_ns=100000000,source_age_ns=1000000000,ce_limit_ns=80000000,
    queues=[8,250,250],gc_original_window=True,rtl_seconds=.020,native_sample_seconds=.040,
    software_step_seconds=1,video_metadata_capacity=64,video_packet_bytes=4096,
    child_download=False,image_ipc=False,automatic_retry=False,heart_algorithm_changed=False,
    qualification_seconds=20,typed_stop_cancellation=True,qualification_requires_fault_free=True,
    preview_owner_process=True,notebook_hardware_imports=False,preflight_before_owner=True,
    preview_ui_returns_on_quarantine=True,browser_prepare_separate_cell=True,
    browser_ready_before_hardware_attempt=True,parent_video_api_loaded=False,
    video_preload_numpy_opencv_only=False,preload_binding_reverified=True,
    video_original_driver_preload=True,video_driver_api_child_local=True,
    prebinding_pl_mapping_count_zero=True,bound_driver_sources_rechecked=True,
    startup_cancel_between_device_stages=True,
    driver_sources_checked_before_download=True,early_exact_bytes_prefix=True,
    startup_failure_cleanup_evidence=True,notebook_single_snapshot_per_check=True)


def startup_deadline_ns(now_ns):
    return now_ns+STARTUP_SECONDS*1_000_000_000


def startup_budget():
    return dict(effective_startup_seconds=STARTUP_SECONDS,reference_startup_seconds=180,
        scope='pre-formal preparation only; cleanup may continue after stop request',
        parent_origin='original drive_owner after start() returns',
        video_origin='original video install/preview creation; parent stop also applies',
        formal_seconds=60,ready_seconds=60,ps_exit_seconds=1,
        retained_reports_are_reference_policy=True)


def with_startup300(original):
    """Keep the frozen owner loop, clocks and cleanup; replace only its startup literals."""
    constants=original.__code__.co_consts
    old_message='所有者启动超过180秒，请求停止并等待真实清理'
    limits=[i for i,x in enumerate(constants) if type(x) is int and x==180]
    messages=[i for i,x in enumerate(constants) if type(x) is str and x==old_message]
    if len(limits)!=1 or len(messages)!=1:
        raise ValueError('reviewed parent startup constant contract changed; no hardware started')
    changed=list(constants)
    changed[limits[0]]=STARTUP_SECONDS
    changed[messages[0]]=f'所有者启动超过{STARTUP_SECONDS}秒，请求停止并等待真实清理'
    result=FunctionType(original.__code__.replace(co_consts=tuple(changed)),original.__globals__,
        original.__name__,original.__defaults__,original.__closure__)
    result.__kwdefaults__=dict(original.__kwdefaults__) if original.__kwdefaults__ is not None else None
    result.__qualname__,result.__module__,result.__doc__=original.__qualname__,original.__module__,original.__doc__
    return result


def read_book_identity(path,expected_manifest_sha256):
    book=json.loads(Path(path).read_bytes())
    if book.get('metadata',{}).get('video_process_manifest_sha256')!=expected_manifest_sha256:
        raise ValueError('Notebook handoff manifest identity differs')
    k=book['metadata']['kernelspec']
    value=[book['nbformat'],k['name'],k['language'],[(c['cell_type'],''.join(c['source'])) for c in book['cells']]]
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def verify(root,expected_manifest_sha256):
    root=Path(root).resolve(strict=True);raw=(root/MANIFEST).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_manifest_sha256:raise ValueError('video process manifest differs')
    d=json.loads(raw)
    if (d.get('schema'),d.get('source_manifest_sha256'),d.get('policy'))!=('real_video_process_v7',SOURCE_SHA,POLICY):
        raise ValueError('video process scope/policy differs')
    book_digest=read_book_identity(root/BOOK,expected_manifest_sha256)
    from journal60_guard import verify as original
    old=original(root,SOURCE_SHA)
    pins=json.loads((root/'journal60-manifest.json').read_bytes())['files']
    expected=set(pins)|{'journal60-manifest.json'}|ADDED
    if set(d['files'])!=expected or d['expected_members']!=len(expected)+1:raise ValueError('video process members differ')
    for name,pin in d['files'].items():
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:raise ValueError('video process path escapes')
        p=root/name
        if p.is_symlink() or not p.resolve(strict=True).is_relative_to(root):raise ValueError('video process file linked')
        if name in pins:
            if pin!=pins[name]:raise ValueError('retained pin changed: '+name)
            continue  # The original full verifier has checked it, including source identities.
        kind='notebook_identity' if name==BOOK else 'bytes'
        digest=book_digest if name==BOOK else hashlib.sha256(p.read_bytes()).hexdigest()
        if pin!={'kind':kind,'sha256':digest}:raise ValueError('video process new member differs: '+name)
    proof=json.loads((root/'video-split-local-evidence.json').read_bytes())
    if (proof.get('hardware_accessed') is not False or proof.get('local_tests_passed') is not True
        or proof.get('saved1505',{}).get('count')!=1505 or proof['saved1505'].get('invalid')!=5
        or proof['saved1505'].get('algorithm_differences')!=0 or proof['saved1505'].get('projection_decision_differences')!=0
        or proof['saved1505'].get('consumer_exitcode')!=0
        or proof['saved1505'].get('source_manifest_sha256')!=SOURCE_SHA
        or proof['saved1505'].get('input_sha256')!='077a209c8612d8ac7d9e697c6300e5265232bfc5f2ecf0c479093a868b62df52'):
        raise ValueError('local video process evidence incomplete')
    if set(proof['code_sha256'])!={n for n in ADDED if n.endswith('.py')}:raise ValueError('local evidence code coverage differs')
    for name,digest in proof['code_sha256'].items():
        if name not in ADDED or hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('local evidence source mismatch')
    for name in ADDED:
        if name.endswith('.py'):
            loaded=sys.modules.get(Path(name).stem)
            if loaded is not None and Path(loaded.__file__).resolve()!=root/name:raise ValueError('mixed video process module: '+name)
    return dict(bundle_validated=True,hardware_accessed=False,manifest_sha256=expected_manifest_sha256,
        preserved_members=old['package_members'],package_members=d['expected_members'],policy=POLICY,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
