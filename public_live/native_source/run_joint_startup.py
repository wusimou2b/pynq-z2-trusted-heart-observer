"""Manual startup diagnosis; original 90s startup and original 60s trial unchanged."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode=True
if __package__:
    from .joint_startup_guard import verify_startup,assess_startup,write_new,sha
    from .joint_startup import replace_attribute
    from .joint_owner import require_board
else:
    from joint_startup_guard import verify_startup,assess_startup,write_new,sha
    from joint_startup import replace_attribute
    from joint_owner import require_board

ROOT=Path(__file__).resolve().parent


def run_startup60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-JOINT-STARTUP5':raise ValueError('requires hardware=True and RUN-JOINT-STARTUP5')
    require_board();checked=verify_startup(ROOT)
    attempt=ROOT/'joint-startup-attempt.json';directory=ROOT/'frozen/live_results/joint-concurrent5-static60'
    if attempt.exists() or (ROOT/'joint-concurrent-attempt.json').exists() or directory.exists():
        raise FileExistsError('已尝试，保留结果；不覆盖、不重跑')
    if __package__:
        from . import joint_concurrent_worker as original,run_joint_concurrent5 as inherited
        from .joint_startup_worker import start_owner
    else:
        import joint_concurrent_worker as original,run_joint_concurrent5 as inherited
        from joint_startup_worker import start_owner
    write_new(attempt,dict(schema='v3b25_startup5_attempt_v1',automatic_retry=False,
        startup_manifest_sha256=checked['startup_manifest_sha256']))
    print('启动分段观测：原90秒保护不变；停止请求可见后不再进入下一启动阶段。准备另计，失败保存、不重跑。',flush=True)
    result={};failure=None
    try:
        with replace_attribute(original,'start_owner',start_owner):
            result=inherited.run_concurrent60(hardware=True,confirmation='RUN-JOINT-5FPS60')
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
    if not directory.exists():directory.mkdir(parents=True,exist_ok=False)
    epoch=None;summary=directory/'capture/summary.json'
    try:
        if summary.is_file():epoch=json.loads(summary.read_text(encoding='utf-8')).get('startup',{}).get('started_ns')
    except Exception as exc:failure=failure or dict(stage='summary_read',type=type(exc).__name__,message=str(exc))
    report=assess_startup(directory,result,formal_epoch=epoch)
    unchanged=True
    try:verify_startup(ROOT)
    except Exception as exc:
        unchanged=False;failure=failure or dict(stage='postrun_identity',type=type(exc).__name__,message=str(exc))
    report.update(inputs_unchanged=unchanged,wrapper_error=failure,startup_manifest_sha256=checked['startup_manifest_sha256'])
    if failure or not unchanged:report['joint_60s_pilot_completed']=False
    report['input_sha256']={p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p.suffix!='.zip'}
    write_new(directory/'joint_startup_result.json',report)
    archive=ROOT/'joint-startup-results.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p.suffix!='.zip':z.write(p,arcname=p.relative_to(directory).as_posix())
    print('启动观测完整：'+str(report['startup_observation_complete'])+'；共同60秒小试完整：'+str(report['joint_60s_pilot_completed']),flush=True)
    print('请回传新总ZIP joint-startup-results.zip；不自动重试。',flush=True)
    from IPython.display import display,FileLink
    display(FileLink(str(archive.relative_to(Path.cwd()))));return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check-bundle',action='store_true');parser.parse_args(argv)
    print(json.dumps(verify_startup(ROOT),ensure_ascii=False));return 0


if __name__=='__main__':sys.exit(main())
