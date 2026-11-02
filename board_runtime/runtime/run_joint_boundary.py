"""Manual original-budget joint trial; bounded observation, no automatic retry."""
import argparse
import json
from pathlib import Path
import sys
import time
import zipfile

sys.dont_write_bytecode=True
if __package__:
    from .joint_boundary_guard import verify_boundary,assess_boundaries,write_new,sha
    from .joint_startup import replace_attribute
    from .joint_owner import require_board
else:
    from joint_boundary_guard import verify_boundary,assess_boundaries,write_new,sha
    from joint_startup import replace_attribute
    from joint_owner import require_board

ROOT=Path(__file__).resolve().parent

def run_boundary60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-JOINT-BOUNDARY5':raise ValueError('requires hardware=True and RUN-JOINT-BOUNDARY5')
    require_board();checked=verify_boundary(ROOT)
    if not callable(getattr(time,'thread_time_ns',None)):raise RuntimeError('thread_time_ns unavailable; no hardware started')
    directory=ROOT/'frozen/live_results/joint-concurrent5-static60';attempt=ROOT/'joint-boundary-attempt.json'
    if attempt.exists() or directory.exists() or any(ROOT.glob('joint-*-attempt.json')) or (ROOT/'joint-boundary-results.zip').exists():
        raise FileExistsError('已尝试或已有结果，保留，不覆盖、不重跑')
    if __package__:
        from . import run_joint_overlap as inherited,joint_overlap_worker as original
        from .joint_boundary_worker import start_owner
    else:
        import run_joint_overlap as inherited,joint_overlap_worker as original
        from joint_boundary_worker import start_owner
    write_new(attempt,dict(schema='v3b25_boundary5_attempt_v1',automatic_retry=False,boundary_manifest_sha256=checked['boundary_manifest_sha256']))
    print('联合边界观测：原25/25Hz＋5fps，原GC/保护/700点重叠预热和关闭策略不变。',flush=True)
    print('新增观测仅内存记录；正式60秒，原收尾完成后导出；失败保存、不自动重试。',flush=True)
    old={};failure=None
    try:
        with replace_attribute(original,'start_owner',start_owner):
            old=inherited.run_overlap60(hardware=True,confirmation='RUN-JOINT-OVERLAP5')
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
    directory.mkdir(parents=True,exist_ok=True)
    result=assess_boundaries(directory,old)
    unchanged=True
    try:verify_boundary(ROOT)
    except BaseException as exc:
        unchanged=False;failure=failure or dict(stage='post_identity',type=type(exc).__name__,message=str(exc))
    result.update(inputs_unchanged=unchanged,wrapper_error=failure,boundary_manifest_sha256=checked['boundary_manifest_sha256'])
    if failure or not unchanged:result['boundary_observation_complete']=result['joint_60s_pilot_completed']=False
    result['input_sha256']={p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p.suffix!='.zip'}
    write_new(directory/'boundary_probe.json',result)
    with (directory/'boundary_probe.txt').open('x',encoding='utf-8') as f:
        f.write('联合边界观测完整：'+str(result['boundary_observation_complete'])+'\n原共同60秒小试完整：'+str(result['joint_60s_pilot_completed'])+'\n'+result['scope_cn']+'\n')
        f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    archive=ROOT/'joint-boundary-results.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p.suffix!='.zip':z.write(p,arcname=p.relative_to(directory).as_posix())
    print('联合边界观测完整：'+str(result['boundary_observation_complete'])+'；不等于修复或完整验收。',flush=True)
    print('请保留最后的新总ZIP joint-boundary-results.zip；不自动重试。',flush=True)
    from IPython.display import display,FileLink
    display(FileLink(str(archive.relative_to(Path.cwd()))));return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-bundle',action='store_true');p.parse_args(argv)
    print(json.dumps(verify_boundary(ROOT),ensure_ascii=False));return 0

if __name__=='__main__':sys.exit(main())
