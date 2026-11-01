"""Manual original shared capture with metadata/deltas and browser-side Canvas."""
import argparse
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED
sys.dont_write_bytecode=True

if __package__:
    from .browser_heart_guard import verify_package,assess_candidate,write_new,sha
    from .browser_heart_display import prepare_browser,ready_bridge,install_browser_display
    from .joint_startup import replace_attribute
else:
    from browser_heart_guard import verify_package,assess_candidate,write_new,sha
    from browser_heart_display import prepare_browser,ready_bridge,install_browser_display
    from joint_startup import replace_attribute

ROOT=Path(__file__).resolve().parent


def run_browser60(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-BROWSER-HEART60':
        raise ValueError('requires hardware=True and RUN-BROWSER-HEART60')
    checked=verify_package(ROOT);bridge=ready_bridge()
    if __package__:from .browser_heart_budget import validate_budget
    else:from browser_heart_budget import validate_budget
    budget=validate_budget(ROOT/'browser-budget.json',checked['package_manifest_sha256'])
    archive=ROOT/'browser-heart-results.zip'
    if archive.exists():raise FileExistsError('已有结果，不覆盖')
    if __package__:
        from . import run_heart_video as original,heart_video_worker as worker
        from .browser_heart_worker import start_owner
    else:
        import run_heart_video as original,heart_video_worker as worker
        from browser_heart_worker import start_owner
    result=None;failure=None;close_error=None
    print('四曲线由电脑浏览器绘制；板端只发送当前状态与新增点。',flush=True)
    try:
        with install_browser_display(ROOT,bridge),replace_attribute(original,'ROOT',ROOT), \
             replace_attribute(original,'verify_package',verify_package), \
             replace_attribute(original,'assess_candidate',assess_candidate), \
             replace_attribute(worker,'start_owner',start_owner):
            result=original.run_joint60(hardware=True,confirmation='RUN-HEART-VIDEO60')
    except BaseException as exc:
        failure=exc
    finally:
        try:bridge.close()
        except BaseException as exc:close_error=dict(type=type(exc).__name__,message=str(exc))
    final=dict(schema='v3b25_browser_display_final_v1',package_manifest_sha256=checked['package_manifest_sha256'],
        bridge=bridge.report(),close_error=close_error,
        display_preparation_budget=budget,
        run_error=dict(type=type(failure).__name__,message=str(failure)) if failure else None,
        browser_render_measured=False,hardware_acceptance_implied=False)
    write_new(ROOT/'browser-display-final.json',final)
    source=ROOT/'joint-concurrent-results.zip'
    if source.is_file():
        with ZipFile(source) as old,ZipFile(archive,'x',compression=ZIP_DEFLATED) as new:
            if len(old.namelist())!=len(set(old.namelist())) or old.testzip() is not None:
                raise ValueError('original result ZIP corrupt')
            for name in old.namelist():new.writestr(name,old.read(name))
            new.write(ROOT/'browser-display-final.json','browser-display-final.json')
        print('结果：browser-heart-results.zip；等待本次收尾完成，不自动重跑。',flush=True)
        from IPython.display import FileLink,display
        display(FileLink(str(archive.relative_to(Path.cwd()))))
    if failure is not None:raise failure
    if close_error is not None:raise RuntimeError('browser close failed; results retained')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check-bundle',action='store_true');p.add_argument('--budget',action='store_true');args=p.parse_args()
    checked=verify_package(ROOT)
    if args.budget:
        if __package__:from .browser_heart_budget import run_budget
        else:from browser_heart_budget import run_budget
        result=run_budget(ROOT,checked)
        print(json.dumps({k:v for k,v in result.items() if k not in ('rounds','initial_sync')},ensure_ascii=False))
    else:print(json.dumps(checked,ensure_ascii=False))
