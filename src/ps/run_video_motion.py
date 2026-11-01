"""Manual complete motion entry; delegate original continuous control and cleanup."""
import argparse
from functools import partial
import json
from pathlib import Path
import platform
import sys
from zipfile import ZipFile, ZIP_DEFLATED

if __package__:
    from .video_motion_guard import verify_package, MANIFEST
else:
    from video_motion_guard import verify_package, MANIFEST

ROOT=Path(__file__).resolve().parent
_PREPARED_SHA=None
_USED=False


def require_board():
    if sys.platform!='linux' or platform.machine()!='armv7l':
        raise RuntimeError('PYNQ ARM Linux only; no desktop hardware authorization')


def prepare():
    global _PREPARED_SHA
    if _PREPARED_SHA is not None:raise RuntimeError('already prepared; preserve first display and stop button')
    checked=verify_package(ROOT)
    if __package__:
        from . import continuous_run as original
        from .joint_startup import replace_attribute
    else:
        import continuous_run as original
        from joint_startup import replace_attribute
    with replace_attribute(original,'ROOT',ROOT):prepared=original.prepare()
    _PREPARED_SHA=checked['manifest_sha256']
    print('完整运动集成：原190秒心率核心＋PL视频统计＋MPU6050融合；持续运行，点击正常停止。',flush=True)
    return dict(prepared,motion=checked)


def export_motion(root,report,*,original_completed):
    root=Path(root)
    with (root/'full-motion-result.json').open('x',encoding='utf-8') as sink:
        json.dump(report,sink,ensure_ascii=False,indent=2,allow_nan=False)
    archive=root/'baseline-motion-results.zip'
    with ZipFile(archive,'x',compression=ZIP_DEFLATED) as dest:
        if original_completed:
            with ZipFile(root/'continuous-results.zip') as original:
                if original.testzip() is not None or len(original.namelist())!=len(set(original.namelist())):
                    raise ValueError('original continuous export corrupt')
                for name in original.namelist():dest.writestr(name,original.read(name))
        # Never inspect possibly active journals following an early exception.
        for name in ('full-motion-result.json',MANIFEST,'shadow-fusion-manifest.json','spatial-artifacts.json','shadow-rule.json'):
            dest.write(root/name,name)
    return archive


def run(*,hardware=False,confirmation=None):
    global _USED
    if hardware is not True or confirmation!='RUN-FULL-MOTION25':
        raise ValueError('requires hardware=True and RUN-FULL-MOTION25')
    require_board()
    checked=verify_package(ROOT,_PREPARED_SHA)
    if _PREPARED_SHA is None or _USED:raise RuntimeError('prepare once before the single manual attempt; no restart')
    if __package__:
        from . import continuous_run as original,continuous_runtime as runtime
        from .video_motion_worker import start_owner
        from .shadow_assessment import audit_shadow_artifacts
        from .joint_startup import replace_attribute
    else:
        import continuous_run as original,continuous_runtime as runtime
        from video_motion_worker import start_owner
        from shadow_assessment import audit_shadow_artifacts
        from joint_startup import replace_attribute
    _USED=True
    result=None;failure=None;identity_error=None;owner=None
    try:
        with replace_attribute(original,'ROOT',ROOT), \
             replace_attribute(original,'audit_artifacts',audit_shadow_artifacts), \
             replace_attribute(runtime,'start_owner',partial(start_owner,motion_manifest_sha=checked['manifest_sha256'])):
            result=original.run(hardware=True,confirmation='RUN-CONTINUOUS25')
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
    try:verify_package(ROOT,checked['manifest_sha256'])
    except BaseException as exc:identity_error=dict(type=type(exc).__name__,message=str(exc))
    if result is not None:
        try:
            with ZipFile(ROOT/'continuous-results.zip') as z:owner=json.loads(z.read('continuous-results/motion-owner.json'))
        except (OSError,KeyError,ValueError) as exc:
            failure=failure or dict(type=type(exc).__name__,message=str(exc))
    owner_ok=bool(owner and owner['inputs_unchanged'] and owner['wrapper_error'] is None
        and owner['video_writer_stopped'] and owner['preparation_hdmi_submissions']==4
        and owner['fusion']['frames']>0 and owner['fusion']['imu']['observations']>0)
    report=dict(schema='v3b25_baseline_full_motion_result_v1',
        integrated_session_passed=bool(result and result['manual_session_passed'] and owner_ok
            and failure is None and identity_error is None),original_continuous_result=result,motion_owner=owner,
        parent_error=failure,identity_error=identity_error,video_and_mpu_fusion_enabled=True,
        heart_control_enabled=False,accuracy_verified=False,board_ddr_verified=False,full_v3b_acceptance_passed=False)
    archive=export_motion(ROOT,report,original_completed=result is not None)
    print('完整集成会话基础检查：'+str(report['integrated_session_passed'])+'；不是三档准确率、DDR或完整V3B验收。',flush=True)
    print('请回传 '+archive.name+'；失败保留，不自动重试。',flush=True)
    from IPython.display import display,FileLink
    display(FileLink(archive.name))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check-bundle',action='store_true',required=True)
    parser.parse_args();print(json.dumps(verify_package(ROOT),ensure_ascii=False))
