"""Manual 25/25Hz heart + 5fps video pilot; CLI only checks package identity."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode=True
if __package__:
    from .joint_concurrent_guard import verify_concurrent,assess_concurrent,write_new,sha
    from .joint_owner import require_board
else:
    from joint_concurrent_guard import verify_concurrent,assess_concurrent,write_new,sha
    from joint_owner import require_board

ROOT=Path(__file__).resolve().parent


def run_concurrent60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-JOINT-5FPS60':
        raise ValueError('requires hardware=True and RUN-JOINT-5FPS60')
    require_board();checked=verify_concurrent(ROOT)
    attempt=ROOT/'joint-concurrent-attempt.json';directory=ROOT/'frozen/live_results/joint-concurrent5-static60'
    if attempt.exists() or directory.exists():raise FileExistsError('已尝试，保留结果；不覆盖、不重跑')
    frozen=ROOT/'frozen'
    if str(frozen) not in sys.path:sys.path.insert(0,str(frozen))
    from entry25_guard import validate,activate
    validate(frozen);activate(frozen)
    import run_entry25_live as inherited
    if __package__:from .joint_concurrent_worker import start_owner
    else:from joint_concurrent_worker import start_owner
    original=inherited._start_entry_owner;failure=None;run={}
    print('共同60秒首次并发：放稳手指；心率25/25Hz、视频目标5fps。只运行本次入口，停止其他任务。',flush=True)
    print('单实际硬件所有者、联合bit仅下载一次；Notebook心率，HDMI动态视频及PL统计。',flush=True)
    print('原模板的原Overlay/raw50/不启动视频脚注不是本次身份；以新增联合报告为准。准备另计，不强杀或自动重试。',flush=True)
    write_new(attempt,dict(schema='v3b25_concurrent_attempt_v1',automatic_retry=False,
        package_manifest_sha256=checked['package_manifest_sha256']))
    inherited._start_entry_owner=start_owner
    try:run=inherited.run_static60(hardware=True,output=directory)
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
    finally:inherited._start_entry_owner=original
    # The unchanged parent joins its owner without force-kill. An unsafe owner
    # remains alive in its backstop, so this point does not free its resources.
    if not directory.exists():directory.mkdir(parents=True,exist_ok=False)
    errors=[]
    def read(name):
        path=directory/name
        if not path.is_file():return {}
        try:return json.loads(path.read_text(encoding='utf-8'))
        except Exception as exc:
            errors.append(dict(file=name,type=type(exc).__name__,message=str(exc)));return {}
    run=read('run_entry25_live.json') or run;owner=read('concurrent_owner_result.json')
    unchanged=True
    try:verify_concurrent(ROOT)
    except Exception as exc:
        unchanged=False;errors.append(dict(stage='postrun_identity',type=type(exc).__name__,message=str(exc)))
    result=assess_concurrent(directory,run,owner,inputs_unchanged=unchanged,
        wrapper_error=failure or (dict(stage='report_read',details=errors) if errors else None))
    result.update(package_manifest_sha256=checked['package_manifest_sha256'],report_errors=errors,
        inherited_report='run_entry25_live.json',owner_report='concurrent_owner_result.json',
        input_sha256={p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob('*'))
            if p.is_file() and p.suffix!='.zip'})
    write_new(directory/'joint_concurrent_result.json',result)
    archive=ROOT/'joint-concurrent-results.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.suffix!='.zip':z.write(path,arcname=path.relative_to(directory).as_posix())
    print('受控5fps并发小试完整：'+str(result['joint_60s_pilot_completed']),flush=True)
    print('未通过项：'+str([k for k,v in result['checks'].items() if not v]),flush=True)
    print(result['scope_cn'],flush=True)
    print('请保留结果，不自动重试；结束后HDMI无信号正常。ZIP：'+str(archive),flush=True)
    from IPython.display import FileLink,display
    display(FileLink(str(archive.relative_to(Path.cwd()))))
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle',action='store_true');parser.parse_args(argv)
    print(json.dumps(verify_concurrent(ROOT),ensure_ascii=False));return 0


if __name__=='__main__':sys.exit(main())
