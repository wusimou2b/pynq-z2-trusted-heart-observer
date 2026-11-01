"""Cold manual camera feature entry; unchanged cooperative wait, no forced kill."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from zipfile import ZipFile,ZIP_DEFLATED

if __package__:
    from .spatial_camera_guard import verify_package,MANIFEST
    from .run_roi_motion import supervise,write_new
else:
    from spatial_camera_guard import verify_package,MANIFEST
    from run_roi_motion import supervise,write_new

PENDING_CHILDREN=[]


def export_results(root,report):
    root=Path(root);stopped=report.get('video',{}).get('thread_exited') is True
    report['journal_writer_stopped']=stopped
    report['journal_exported']=bool(stopped and (root/'results/frames.jsonl').is_file())
    write_new(root/'results/report.json',report)
    with ZipFile(root/'spatial-camera-results.zip','x',compression=ZIP_DEFLATED) as z:
        z.write(root/'results/report.json','report.json')
        if stopped:
            for name in ('frames.jsonl','feature-summary.json'):
                if (root/'results'/name).is_file():z.write(root/'results'/name,name)
        z.write(root/MANIFEST,MANIFEST);z.write(root/'spatial-artifacts.json','spatial-artifacts.json')


def worker(root):
    verify_package(root)
    if sys.platform!='linux' or platform.machine()!='armv7l':raise RuntimeError('PYNQ ARM Linux only')
    retained=None
    try:from spatial_camera import run_session
    except BaseException as exc:
        (root/'results').mkdir(exist_ok=False)
        report=dict(schema='v3b25_spatial_camera_run_v1',session_complete=False,fault=dict(stage='runtime_import',type=type(exc).__name__,message=str(exc)),
            cleanup=dict(cleanup_complete=True,quarantine_required=False,hardware_open_not_attempted=True),
            heart_capture_started=False,heart_ps_started=False,imu_capture_started=False,images_saved=False,classification_performed=False,
            thresholds_refitted=False,three_class_acceptance_passed=False,board_ddr_verified=False,full_v3b_acceptance_passed=False)
    else:report,retained=run_session(root,root/'results')
    try:verify_package(root);report['inputs_unchanged']=True
    except BaseException as exc:report.update(inputs_unchanged=False,post_identity_error=str(exc),session_complete=False)
    try:
        export_results(root,report)
        print('相机空间特征采集完整：',report['session_complete'],'；不是三档识别、心率联合或DDR验收。',flush=True)
        if not report['journal_writer_stopped']:print('日志writer未确认停止，ZIP不读取活跃日志；请保留原目录。',flush=True)
        print('请回传 spatial-camera-results.zip 和完整输出；失败保留，不重跑。',flush=True)
    finally:
        if retained is not None:
            print('QUARANTINE：停止未确认，保留所有者/缓冲/锁；保持单元，不重跑或启动其它入口。',flush=True)
            while True:time.sleep(1)
    return 0 if report['session_complete'] else 1


def launch_once(root,*,confirmation):
    root=Path(root).resolve();verify_package(root)
    if confirmation!='RUN-SPATIAL-CAMERA':raise ValueError('manual camera/HDMI/PL replacement confirmation required')
    if sys.platform!='linux' or platform.machine()!='armv7l':raise RuntimeError('PYNQ ARM Linux only')
    for name in ('attempt.json','results','camera.log','stop.request','spatial-camera-results.zip','formal-ready.json','launch-result.json'):
        if (root/name).exists():raise FileExistsError('prior attempt exists; preserve and do not retry')
    write_new(root/'attempt.json',dict(started_monotonic_ns=time.monotonic_ns()))
    with (root/'camera.log').open('xb') as log:
        child=subprocess.Popen([sys.executable,'-B','-u',str(root/'run_spatial_camera.py'),'--worker'],cwd=root,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        PENDING_CHILDREN.append(child);write_new(root/'child.json',dict(pid=child.pid));position=0
        def show():
            nonlocal position
            with (root/'camera.log').open('rb') as f:f.seek(position);data=f.read();position=f.tell()
            if data:print(data.decode('utf-8',errors='replace'),end='',flush=True)
        status=supervise(child,root,show=show)
        if status['worker_exited']:PENDING_CHILDREN.remove(child)
        else:print('未确认安全收尾；未强杀，请保留页面和输出。',flush=True)
    status['archive_exists']=(root/'spatial-camera-results.zip').is_file()
    write_new(root/'launch-result.json',status);return status


if __name__=='__main__':
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--check-bundle',action='store_true');g.add_argument('--worker',action='store_true')
    args=p.parse_args();root=Path(__file__).resolve().parent
    if args.check_bundle:print(json.dumps(verify_package(root)));raise SystemExit(0)
    raise SystemExit(worker(root))
