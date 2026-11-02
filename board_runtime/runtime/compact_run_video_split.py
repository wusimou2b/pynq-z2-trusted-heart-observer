"""Manual gates for real video-process ownership; no hardware on import."""
from functools import partial
import json
import multiprocessing as mp
from pathlib import Path
import time
import uuid
from zipfile import ZipFile,ZIP_DEFLATED

if __package__:
    from .video_split_guard import verify,SOURCE_SHA,MANIFEST,startup_deadline_ns,startup_budget,with_startup300
else:
    from video_split_guard import verify,SOURCE_SHA,MANIFEST,startup_deadline_ns,startup_budget,with_startup300

ROOT=Path(__file__).resolve().parent
_ACTIVE_PREVIEWS=[]
_JOINT_PREPARED=None


def write(path,data):
    with path.open('x',encoding='utf-8') as sink:json.dump(data,sink,ensure_ascii=False,indent=2,allow_nan=False)


def short(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    if (ROOT/'video-process-short.json').exists():raise FileExistsError('existing short; preserve, no retry')
    import run_journal60 as original,run_lean_ps,lean_ps_worker
    from joint_startup import replace_attribute
    if __package__:from .video_split_runtime import verified_heart_entry
    else:from video_split_runtime import verified_heart_entry
    old=run_lean_ps.run_short
    def guarded(*args,**kwargs):
        delegate=lean_ps_worker.ps_worker
        target=partial(verified_heart_entry,delegate=delegate,root=ROOT,manifest_sha256=expected_manifest_sha256)
        with replace_attribute(lean_ps_worker,'ps_worker',target):return old(*args,**kwargs)
    report=None;failure=None
    try:
        with replace_attribute(run_lean_ps,'run_short',guarded):report=original.short(expected_manifest_sha256=SOURCE_SHA)
    except BaseException as exc:failure=exc
    result=dict(schema='real_video_process_short_v1',manifest_sha256=expected_manifest_sha256,
        passed=bool(report and report.get('passed')),original=report,hardware_accessed=False,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)))
    write(ROOT/'video-process-short.json',result)
    if failure is not None:raise failure
    if not result['passed']:raise RuntimeError('original PS short exit failed; do not continue')
    return result


def require_short(expected):
    proof=json.loads((ROOT/'video-process-short.json').read_bytes())
    if (proof.get('manifest_sha256')!=expected or proof.get('passed') is not True or proof.get('hardware_accessed') is not False):
        raise ValueError('new identity/PS short exit gate required')


def ownership_passed(result):
    video=result.get('video') or {};detail=video.get('resource_details') or {}
    reference=detail.get('post_verification') or {}
    elapsed=result.get('formal_elapsed_seconds')
    if (result.get('error') is not None or result.get('cleanup_error') is not None
        or result.get('requested_seconds')!=20 or type(elapsed) not in (int,float) or not 20<=elapsed<1e9
        or result.get('cleanup_complete') is not True or 'fault' not in video or video['fault'] is not None
        or video.get('stop_reason') not in ('stop_requested','duration_complete')
        or video.get('process_exitcode')!=0 or video.get('process_alive') is not False
        or video.get('metrics',{}).get('completed_frames',0)<3
        or reference.get('matched') is not True or 'original_video_fault' not in detail):
        return False
    raw=detail['original_video_fault']
    if raw is not None:
        request=detail.get('stop_request_ns');observed=detail.get('cancellation_observed_ns')
        return bool(raw.get('type')=='UserStop' and detail.get('expected_stop_cancellation') is True
            and detail.get('stop_was_requested') is True and type(request) is int and type(observed) is int
            and 0<request<=observed and 0<=detail.get('cancelled_inflight_frames',0)<=1)
    return not detail.get('expected_stop_cancellation',False)


def qualify20(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-VIDEO-PROCESS20':raise ValueError('explicit RUN-VIDEO-PROCESS20 required')
    checked=verify(ROOT,expected_manifest_sha256);require_short(expected_manifest_sha256)
    directory=ROOT/'video-process20';directory.mkdir(exist_ok=False)
    output=directory/'video';output.mkdir()
    write(directory/'attempt.json',dict(manifest_sha256=expected_manifest_sha256,automatic_retry=False,startup_budget=startup_budget(),
        scope='video process ownership qualification only; no heart/sensor capture'))
    if __package__:from .video_split_preview import PreviewSession
    else:from video_split_preview import PreviewSession
    preview=PreviewSession(mp.get_context('spawn'),dict(root=str(ROOT),directory=str(directory),
        manifest_sha256=expected_manifest_sha256,startup_deadline_ns=startup_deadline_ns(time.monotonic_ns())))
    _ACTIVE_PREVIEWS.append(preview);preview.start()
    print('启动独立硬件所有者；Notebook不加载PYNQ、不保留PL映射。',flush=True)
    try:result=preview.wait()
    except KeyboardInterrupt:
        preview.request_stop()
        print('已请求正常停止，等待资源释放；请勿再次中断。',flush=True)
        result=preview.wait()
    result['startup_budget']=startup_budget()
    owner=result.get('coordinator') or {}
    result['hardware_cleanup_complete']=result.get('cleanup_complete') is True
    result['cleanup_complete']=bool(result['hardware_cleanup_complete'] and owner.get('exitcode')==0
        and owner.get('natural_exit') is True and owner.get('alive') is False)
    result['ownership_qualification_passed']=bool(ownership_passed(result) and owner.get('exitcode')==0
        and owner.get('natural_exit') is True and owner.get('alive') is False)
    write(directory/'coordinator-final.json',result)
    with ZipFile(ROOT/'video-process20-results.zip','x',compression=ZIP_DEFLATED) as archive:
        members=directory.rglob('*') if preview.control.saved.is_set() else (directory/'attempt.json',directory/'coordinator-final.json')
        for path in members:
            if path.is_file():archive.write(path,str(path.relative_to(ROOT)))
        archive.write(ROOT/MANIFEST,MANIFEST)
    if owner.get('retained'):
        print('QUARANTINE：结果已保存，实际所有者仍保留资源；不重跑、不加载其它电路。',flush=True)
    elif not result['ownership_qualification_passed']:
        print('本次未通过；结果已保存，未自动重试。',flush=True)
    if not owner.get('alive'):_ACTIVE_PREVIEWS.remove(preview)
    return result


def _run_owned_preview20(*,expected_manifest_sha256,control,startup_deadline_ns):
    """Child-only physical body. All PL/driver references die with this owner."""
    directory=ROOT/'video-process20';output=directory/'video'
    result=dict(schema='real_video_process_ownership20_v3',manifest_sha256=expected_manifest_sha256,
        hardware_owner_pid=__import__('os').getpid(),
        requested_seconds=20,startup_budget=startup_budget(),scope='video-only physical qualification, not concurrent heart25/video5 acceptance',
        heart_capture_started=False,sensor_capture_started=False,child_bitstream_downloaded=False,
        error=None,cleanup_error=None,cleanup_complete=False,ownership_qualification_passed=False,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False,automatic_retry=False)
    owner=runner=None
    startup_deadline=startup_deadline_ns
    try:
        # Refuse before constructing an owner or acquiring its lease. The
        # original immediately-before-download guard remains in place too.
        from main_heart_preflight import require_pl_free
        result['occupancy_before_owner']=require_pl_free()
        from main_spatial_owner import IntegratedOwner
        if __package__:
            from .video_split_process import ProcessVideo
            from .video_split_state import StateChannel
        else:
            from video_split_process import ProcessVideo
            from video_split_state import StateChannel
        from lean_ps_worker import load_original
        load_original(ROOT/'frozen')
        if time.monotonic_ns()>=startup_deadline:raise TimeoutError('startup300s deadline reached before open')
        owner=IntegratedOwner(ROOT/'hardware');identity=owner.open()
        if time.monotonic_ns()>=startup_deadline:raise TimeoutError('startup300s deadline reached after open')
        epoch=uuid.uuid4().hex;ctx=mp.get_context('spawn');channel=StateChannel(ctx,epoch,expected_manifest_sha256)
        runner=ProcessVideo(ctx,dict(root=str(ROOT),output=str(output),run_epoch=epoch,
            manifest_sha256=expected_manifest_sha256,owner_identity=identity,
            vision_epoch=int(owner._io['vision_0'].read(0x18)),startup_deadline_ns=startup_deadline),channel,parent_stop=control.stop)
        result['identity']=runner.prepare();runner.start();formal=time.monotonic_ns();runner.arm(formal)
        control.mark_ready(formal)
        while time.monotonic_ns()-formal<20_000_000_000:
            runner.heartbeat()
            if control.stop.is_set():result['manual_stop_requested']=True;break
            if runner.fault:raise RuntimeError(runner.fault['message'])
            time.sleep(.02)
        result['formal_elapsed_seconds']=(time.monotonic_ns()-formal)/1e9
    except BaseException as exc:result['error']=dict(type=type(exc).__name__,message=str(exc))
    finally:
        try:
            if runner is not None and runner.process is not None:
                runner.request_stop()
                while not runner.wait_loop_stopped(.1):pass  # Same retain-until-native-return boundary.
                result['cleanup']=runner.release(owner);result['video']=runner.report()
            elif owner is not None:
                cleanup=owner.close();result['cleanup']=cleanup
                if cleanup.get('cleanup_complete'):owner.release_after_buffers(buffers_released=True)
            else:result['cleanup']=dict(cleanup_complete=True,no_owner_constructed=True)
            result['cleanup_complete']=result['cleanup'].get('cleanup_complete') is True
        except BaseException as exc:result['cleanup_error']=dict(type=type(exc).__name__,message=str(exc))
        if runner is not None:result['video']=runner.report()
        result['ownership_qualification_passed']=ownership_passed(result)
        try:control.store_result(result)
        finally:
            if not result['cleanup_complete']:
                # Retain the physical owner/CMA in this disposable child, not
                # in a permanently busy Notebook. No automatic stop/free retry.
                while True:time.sleep(1)
    return result


def require_preview(expected_manifest_sha256):
    proof=json.loads((ROOT/'video-process20/coordinator-final.json').read_bytes())
    if (proof.get('manifest_sha256')!=expected_manifest_sha256 or proof.get('ownership_qualification_passed') is not True
            or not ownership_passed(proof) or proof.get('coordinator',{}).get('natural_exit') is not True
            or proof['coordinator'].get('exitcode')!=0 or proof['coordinator'].get('alive') is not False):
        raise ValueError('physical video ownership/release qualification required before joint60')


def prepare_joint60(*,expected_manifest_sha256):
    """Return to the kernel so its original browser clock handshake can run."""
    global _JOINT_PREPARED
    verify(ROOT,expected_manifest_sha256);require_short(expected_manifest_sha256)
    require_preview(expected_manifest_sha256)
    if _JOINT_PREPARED is not None:raise RuntimeError('browser already prepared; preserve the first display')
    import run_journal60 as original,continuous_run as parent
    prepared=original.prepare(expected_manifest_sha256=SOURCE_SHA)
    context=parent._PREPARED
    if context is None or context.get('bridge') is None:raise RuntimeError('original browser preparation did not produce a bridge')
    _JOINT_PREPARED=(expected_manifest_sha256,context)
    print('本单元无硬件。等待上方绿色绘图就绪提示，再单独运行下一个启动单元；不要Run All。',flush=True)
    return dict(prepared=True,hardware_accessed=False,original=prepared)


def joint60(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-VIDEO-PROCESS60':raise ValueError('explicit RUN-VIDEO-PROCESS60 required')
    verify(ROOT,expected_manifest_sha256);require_short(expected_manifest_sha256)
    require_preview(expected_manifest_sha256)
    import continuous_run as parent
    if (_JOINT_PREPARED is None or _JOINT_PREPARED[0]!=expected_manifest_sha256
            or parent._PREPARED is not _JOINT_PREPARED[1]):
        raise RuntimeError('separate browser preparation required; run the display cell and wait for green')
    parent._PREPARED['bridge'].require_ready()
    if (ROOT/'video-process60-attempt.json').exists():raise FileExistsError('joint attempt exists; preserve, no retry')
    candidate_drive=with_startup300(parent.drive_owner)
    budget=startup_budget()
    budget['parent_loop_calls']=0
    def drive(*args,**kwargs):
        budget['parent_loop_calls']+=1
        return candidate_drive(*args,**kwargs)
    write(ROOT/'video-process60-attempt.json',dict(manifest_sha256=expected_manifest_sha256,automatic_retry=False,startup_budget=budget))
    import run_journal60 as original,journal60_runtime as runtime
    from joint_startup import replace_attribute
    if __package__:from .video_split_runtime import start_owner,assess_startup_cleanup
    else:from video_split_runtime import start_owner,assess_startup_cleanup
    failure=None;result=None
    try:
        with replace_attribute(parent,'drive_owner',drive), \
                replace_attribute(runtime,'start_owner',partial(start_owner,expected_split_manifest_sha256=expected_manifest_sha256)), \
                replace_attribute(parent,'assess_manual',partial(assess_startup_cleanup,
                    delegate=parent.assess_manual,directory=ROOT/'continuous-results')):
            result=original.run(hardware=True,confirmation='RUN-JOURNAL60',expected_manifest_sha256=SOURCE_SHA)
    except BaseException as exc:failure=exc
    final=dict(schema='real_video_process_joint60_v1',manifest_sha256=expected_manifest_sha256,result=result,startup_budget=budget,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        automatic_retry=False,live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
    write(ROOT/'video-process60-final.json',final)
    with ZipFile(ROOT/'video-process60-results.zip','x',compression=ZIP_DEFLATED) as archive:
        for name in (MANIFEST,'video-process60-attempt.json','video-process60-final.json','journal60-results.zip'):
            if (ROOT/name).is_file():archive.write(ROOT/name,name)
    if failure is not None:raise failure
    return final
