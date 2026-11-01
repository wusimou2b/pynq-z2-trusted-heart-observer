"""Manual Notebook heart-only entry. CLI only verifies files, never hardware."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode=True
from joint_heart_guard import verify_package,write_new,sha,changed_files,assess_joint

ROOT=Path(__file__).resolve().parent


def run_static60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!="RUN-JOINT-HEART25":
        raise ValueError("requires hardware=True and explicit RUN-JOINT-HEART25 confirmation")
    from joint_owner import require_board
    require_board()
    checked=verify_package(ROOT)
    tracked=json.loads((ROOT/"joint-heart-manifest.json").read_text(encoding="utf-8"))["files"]
    attempt=ROOT/"joint-heart-attempt.json"
    directory=ROOT/"frozen/live_results/joint-heart-static60"
    if attempt.exists() or directory.exists():
        raise FileExistsError("本目录已尝试过，保留结果，不要重复或覆盖")
    frozen=ROOT/"frozen"
    if str(frozen) not in sys.path:
        sys.path.insert(0,str(frozen))
    from entry25_guard import validate,activate
    validate(frozen); activate(frozen)
    import run_entry25_live as inherited
    from joint_heart_worker import start_owner
    original_start=inherited._start_entry_owner
    original_owner=original_run={}
    failure=None
    print("联合电路心率单测：请放稳手指；只运行这一次，正式60秒，预热另计。",flush=True)
    print("本次只加载联合bit一次，不启动USB相机/HDMI/视觉送帧。",flush=True)
    print("下方冻结模板中‘原Overlay/位流不变/raw50’仅描述原参考；实际身份以joint_heart_result.json为准。",flush=True)
    write_new(attempt,dict(schema="joint_heart_attempt_v1",automatic_retry=False,
                           package_manifest_sha256=checked["package_manifest_sha256"]))
    inherited._start_entry_owner=start_owner
    try:
        original_run=inherited.run_static60(hardware=True,output=directory)
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
    finally:
        inherited._start_entry_owner=original_start
    # Original run returns only after its owner join/cleanup, or raises after
    # its own finally. Never start another collector or force-kill an owner.
    if not directory.exists():
        directory.mkdir(parents=True,exist_ok=False)
    def read(name):
        path=directory/name
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    original_run=read("run_entry25_live.json") or original_run
    original_owner=read("joint_owner_result.json")
    changed=changed_files(ROOT,tracked)
    result=assess_joint(original_run,original_owner,inputs_unchanged=not changed,wrapper_error=failure)
    result.update(package_manifest_sha256=checked["package_manifest_sha256"],
                  changed_files=changed,inherited_report="run_entry25_live.json",
                  joint_owner_report="joint_owner_result.json",
                  input_sha256={p.relative_to(directory).as_posix():sha(p) for p in directory.rglob("*") if p.is_file() and p.suffix!=".zip"})
    write_new(directory/"joint_heart_result.json",result)
    archive=ROOT/"joint-heart-results.zip"
    with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_DEFLATED) as package:
        for path in sorted(directory.rglob("*")):
            if path.is_file() and path.suffix!=".zip":
                package.write(path,arcname=path.relative_to(directory).as_posix())
    print("联合电路25Hz心率静止小试："+str(result["joint_heart_static_pilot_completed"]),flush=True)
    print("未通过项："+str([k for k,v in result["checks"].items() if not v]),flush=True)
    print("不是视频并发、准确率、严格实时、DDR或完整V3B验收；保留结果，不自动重试。",flush=True)
    from IPython.display import FileLink,display
    display(FileLink(str(archive.relative_to(Path.cwd()))))
    return result


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-bundle",action="store_true")
    parser.parse_args()
    print(json.dumps(verify_package(ROOT),ensure_ascii=False))
