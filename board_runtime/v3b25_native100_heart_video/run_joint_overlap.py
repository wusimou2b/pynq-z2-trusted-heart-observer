"""Manual original-budget joint trial with pure-PS warmup overlapping preparation."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode=True
if __package__:
    from .joint_overlap_guard import verify_overlap,assess_overlap,write_new,sha
    from .joint_startup import replace_attribute
    from .joint_owner import require_board
else:
    from joint_overlap_guard import verify_overlap,assess_overlap,write_new,sha
    from joint_startup import replace_attribute
    from joint_owner import require_board

ROOT=Path(__file__).resolve().parent


def run_overlap60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-JOINT-OVERLAP5':raise ValueError('requires hardware=True and RUN-JOINT-OVERLAP5')
    require_board();checked=verify_overlap(ROOT)
    attempt=ROOT/'joint-overlap-attempt.json';directory=ROOT/'frozen/live_results/joint-concurrent5-static60'
    if attempt.exists() or (ROOT/'joint-startup-attempt.json').exists() or directory.exists():raise FileExistsError('已尝试，不覆盖、不重跑')
    if __package__:
        from . import joint_startup_worker as original,run_joint_startup as inherited
        from .joint_overlap_worker import start_owner
    else:
        import joint_startup_worker as original,run_joint_startup as inherited
        from joint_overlap_worker import start_owner
    write_new(attempt,dict(schema='v3b25_overlap_attempt_v1',automatic_retry=False,
        overlap_manifest_sha256=checked['overlap_manifest_sha256']))
    print('原700点纯PS预热与硬件准备重叠；原90秒/60秒预热保护不变，不增加计算进程或再次预热。',flush=True)
    startup={};failure=None
    try:
        with replace_attribute(original,'start_owner',start_owner):
            startup=inherited.run_startup60(hardware=True,confirmation='RUN-JOINT-STARTUP5')
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
    if not directory.exists():directory.mkdir(parents=True,exist_ok=False)
    report=assess_overlap(directory,startup)
    unchanged=True
    try:verify_overlap(ROOT)
    except Exception as exc:
        unchanged=False;failure=failure or dict(stage='postrun_identity',type=type(exc).__name__,message=str(exc))
    report.update(inputs_unchanged=unchanged,wrapper_error=failure,overlap_manifest_sha256=checked['overlap_manifest_sha256'])
    if failure or not unchanged:report['overlap_candidate_completed']=report['joint_60s_pilot_completed']=False
    report['input_sha256']={p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p.suffix!='.zip'}
    write_new(directory/'joint_overlap_result.json',report)
    archive=ROOT/'joint-overlap-results.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p.suffix!='.zip':z.write(p,arcname=p.relative_to(directory).as_posix())
    print('观测到启动重叠：'+str(report['overlap_observed'])+'；共同60秒候选完整：'+str(report['overlap_candidate_completed']),flush=True)
    print('请回传最后的新总ZIP joint-overlap-results.zip；失败保留，不自动重试。',flush=True)
    from IPython.display import display,FileLink
    display(FileLink(str(archive.relative_to(Path.cwd()))));return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--check-bundle',action='store_true');parser.parse_args(argv)
    print(json.dumps(verify_overlap(ROOT),ensure_ascii=False));return 0


if __name__=='__main__':sys.exit(main())
