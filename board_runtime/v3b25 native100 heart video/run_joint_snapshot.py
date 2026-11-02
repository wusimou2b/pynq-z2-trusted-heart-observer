"""Manual one-shot candidate. Delegate the unchanged boundary trial and cleanup."""
import argparse
import json
from pathlib import Path
import sys
import zipfile
sys.dont_write_bytecode=True
if __package__:
    from .joint_snapshot_guard import verify_snapshot,assess_snapshot,write_new,sha
    from .joint_startup import replace_attribute
    from .joint_owner import require_board
else:
    from joint_snapshot_guard import verify_snapshot,assess_snapshot,write_new,sha
    from joint_startup import replace_attribute
    from joint_owner import require_board

ROOT=Path(__file__).resolve().parent

def run_snapshot60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-JOINT-SNAPSHOT5':raise ValueError('requires hardware=True and RUN-JOINT-SNAPSHOT5')
    require_board();checked=verify_snapshot(ROOT)
    directory=ROOT/'frozen/live_results/joint-concurrent5-static60'
    # The inherited boundary guard rejects joint-*-attempt.json. Keep its
    # original protection intact, using a distinct candidate marker namespace.
    attempt=ROOT/'snapshot5-attempt.json'
    archive=ROOT/'joint-snapshot-results.zip'
    if attempt.exists() or directory.exists() or any(ROOT.glob('joint-*-attempt.json')) or archive.exists():
        raise FileExistsError('已尝试或已有结果，保留，不覆盖、不重跑')
    if __package__:
        from . import run_joint_boundary as inherited,joint_boundary_worker as original
        from .joint_snapshot_worker import start_owner
    else:
        import run_joint_boundary as inherited,joint_boundary_worker as original
        from joint_snapshot_worker import start_owner
    write_new(attempt,dict(schema='v3b25_snapshot5_attempt_v1',automatic_retry=False,
        snapshot_manifest_sha256=checked['snapshot_manifest_sha256']))
    print('状态快照单次构造候选：25/25Hz＋5fps，原安全guard/GC/保护/预热/关闭策略不变。',flush=True)
    old={};failure=None
    try:
        with replace_attribute(original,'start_owner',start_owner):
            old=inherited.run_boundary60(hardware=True,confirmation='RUN-JOINT-BOUNDARY5')
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc))
    directory.mkdir(parents=True,exist_ok=True)
    result=assess_snapshot(directory,old)
    unchanged=True
    try:verify_snapshot(ROOT)
    except BaseException as exc:
        unchanged=False;failure=failure or dict(stage='post_identity',type=type(exc).__name__,message=str(exc))
    result.update(inputs_unchanged=unchanged,wrapper_error=failure,
        snapshot_manifest_sha256=checked['snapshot_manifest_sha256'])
    if failure or not unchanged:result['snapshot_candidate_completed']=result['joint_60s_pilot_completed']=False
    result['input_sha256']={p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p.suffix!='.zip'}
    write_new(directory/'snapshot_probe.json',result)
    with (directory/'snapshot_probe.txt').open('x',encoding='utf-8') as f:
        f.write('快照候选小试完整：'+str(result['snapshot_candidate_completed'])+'\n'+result['scope_cn']+'\n')
        f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p.suffix!='.zip':z.write(p,arcname=p.relative_to(directory).as_posix())
    print('快照候选小试完整：'+str(result['snapshot_candidate_completed'])+'；不是完整验收。',flush=True)
    print('请保留最后joint-snapshot-results.zip；失败不自动重试。',flush=True)
    from IPython.display import display,FileLink
    display(FileLink(str(archive.relative_to(Path.cwd()))))
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-bundle',action='store_true');p.parse_args(argv)
    print(json.dumps(verify_snapshot(ROOT),ensure_ascii=False));return 0

if __name__=='__main__':sys.exit(main())
