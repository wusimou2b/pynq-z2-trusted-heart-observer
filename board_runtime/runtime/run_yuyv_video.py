"""Manual single video pilot entry. Cold checks never import NumPy or PYNQ."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import zipfile

SOURCES={'run_yuyv_video.py','yuyv_runtime.py','yuyv_transport.py','yuyv_owner.py','yuyv_reference.py',
         'joint_owner.py','joint_video_transport.py','joint_video_runtime.py','joint_video_guard.py',
         'vision_reference.py','README_YUYV_VIDEO.md','yuyv-artifacts.json',
         'heart_v3b25_yuyv.bit','heart_v3b25_yuyv.hwh'}
PENDING_CHILDREN=[]


def write_new(path,obj):
    with path.open('x',encoding='utf-8') as stream:json.dump(obj,stream,ensure_ascii=False,indent=2,allow_nan=False)


def code_identity(nb):
    source=[''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code']
    return hashlib.sha256(json.dumps(source,ensure_ascii=False).encode()).hexdigest()


def verify_package(root):
    root=Path(root)
    manifest=json.loads((root/'yuyv-video-manifest.json').read_text('utf-8'))
    if (manifest.get('schema')!='v3b25_yuyv_video_package_v1' or set(manifest.get('files',{}))!=SOURCES
        or manifest.get('formal_seconds')!=20 or manifest.get('target_fps')!=5):raise ValueError('video scope/file identity mismatch')
    for name,expected in manifest['files'].items():
        path=root/name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('video source identity mismatch: '+name)
    if code_identity(json.loads((root/'YuyvVideo.ipynb').read_text('utf-8')))!=manifest['notebook_code_sha256']:
        raise ValueError('executable Notebook changed')
    return manifest


def worker(root):
    if sys.platform!='linux' or platform.machine()!='armv7l':raise RuntimeError('board ARM Linux only')
    verified=verify_package(root)
    output=root/'results';output.mkdir(exist_ok=False)
    report={'schema':'v3b25_yuyv_video_run_v1','fault':None,'cleanup':{},'screen_dynamic_observed':None,
            'requested_formal_seconds':20,'target_application_fps':5,'heart_capture_started':False,
            'board_ddr_verified':False,'joint_acceptance_passed':False,'full_v3b_acceptance_passed':False,
            'source_sha256':verified['files'],'images_saved':False,'frames':[]}
    resources=None;formal=None;slot=0;start=time.monotonic()
    try:
        from yuyv_runtime import Resources
        from yuyv_transport import validate_yuyv
        stopped=lambda:(root/'stop.request').exists()
        resources=Resources(root,cancelled=stopped,on_event=lambda e:None)
        print('启动新YUYV联合电路，心率关闭；启动与正式20秒分开计。',flush=True)
        report['identity']=resources.open();report['startup_seconds']=time.monotonic()-start
        formal=time.monotonic();end=formal+20
        print('READY：正式20秒动态画面开始，目标5fps；请观察屏幕并缓慢移动物体。',flush=True)
        while time.monotonic()<end:
            if stopped():raise RuntimeError('user stop requested')
            if not resources.camera.grab():raise RuntimeError('camera grab failed')
            now=time.monotonic()
            if now<formal+slot/5:continue
            if now>=end:break
            ok,raw=resources.camera.retrieve();read_ns=time.monotonic_ns()
            if not ok:raise RuntimeError('raw camera retrieve failed')
            validate_yuyv(raw,camera_geometry=True)
            if time.monotonic()>=end:break
            late=max(0,int((time.monotonic()-(formal+slot/5))*5));slot+=late
            t0,c0=time.monotonic_ns(),time.thread_time_ns()
            row=resources.process_ready_frame(raw,sequence=len(report['frames']),timestamp_ns=read_ns)
            row['processing_wall_ns']=time.monotonic_ns()-t0;row['processing_thread_cpu_ns']=time.thread_time_ns()-c0
            row['missed_target_slots']=late;report['frames'].append(row);slot+=1
            if len(report['frames'])%25==0:print('已提交',len(report['frames']),'帧；正式',round(time.monotonic()-formal,2),'秒',flush=True)
        report['stop_reason']='duration_complete'
    except BaseException as exc:
        report['stop_reason']='fault';report['fault']={'stage':getattr(resources,'stage','imports'),'type':type(exc).__name__,'message':str(exc)}
    finally:
        report['formal_elapsed_seconds']=None if formal is None else time.monotonic()-formal
        print('收尾：停止相机与三个DMA，确认停止后释放缓冲。',flush=True)
        if resources is not None:
            try:report['cleanup']=resources.close()
            except BaseException as exc:report['cleanup']={'cleanup_complete':False,'quarantine_required':True,'error':str(exc)}
    if resources is not None and report['cleanup'].get('cleanup_complete'):
        try:report['post_verification']=resources.post_verify()
        except BaseException as exc:report['post_verification']={'matched':False,'error':str(exc)}
    report['counts']={'captured':getattr(resources,'captured',0),'submitted':getattr(resources,'submitted',0),
                      'pl_completed':getattr(getattr(resources,'port',None),'completed',0),'records':len(report['frames'])}
    n=len(report['frames']);elapsed=report['formal_elapsed_seconds'] or 0
    report['application_submit_fps']=n/elapsed if elapsed else None
    report['target_5fps_observed']=bool(elapsed and n/elapsed>=5)
    report['basic_checks']={
        'full_duration':report['stop_reason']=='duration_complete' and elapsed>=20,
        'no_fault':report['fault'] is None,
        'exact_counts':n>=3 and all(v==n for v in report['counts'].values()),
        'source_alignment':all(r['source_sequence']==i and r['vision']['frame_index']==i and r['vision']['source_sequence']==i for i,r in enumerate(report['frames'])),
        'post_reference':report.get('post_verification',{}).get('matched') is True and report.get('post_verification',{}).get('compared_frames')==2,
        'cleanup':report['cleanup'].get('cleanup_complete') is True}
    report['basic_trial_complete']=all(report['basic_checks'].values())
    try:verify_package(root);report['inputs_unchanged']=True
    except BaseException as exc:report['inputs_unchanged']=False;report['post_identity_error']=str(exc);report['basic_trial_complete']=False
    try:
        write_new(output/'report.json',report)
        with zipfile.ZipFile(root/'yuyv-video-results.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
            z.write(output/'report.json','report.json')
            for name in ('yuyv-video-manifest.json','yuyv-artifacts.json'):z.write(root/name,name)
        print('独立视频基础检查：',report['basic_trial_complete'],'；实际画面待你确认。',flush=True)
        print('结果：yuyv-video-results.zip；故障：',report['fault'],flush=True)
    finally:
        if report['cleanup'].get('quarantine_required'):
            try:print('QUARANTINE：收尾未确认，保留进程/缓冲/锁；不要再运行或关闭内核。',flush=True)
            except BaseException:pass
            while True:time.sleep(1)
    return 0 if report['basic_trial_complete'] else 1


def launch_once(root):
    root=Path(root).resolve();verify_package(root)
    if sys.platform!='linux' or platform.machine()!='armv7l':raise RuntimeError('board ARM Linux only')
    for name in ('attempt.json','results','camera.log','yuyv-video-results.zip'):
        if (root/name).exists():raise FileExistsError('existing attempt/result; do not retry')
    write_new(root/'attempt.json',{'started_monotonic_ns':time.monotonic_ns()})
    with (root/'camera.log').open('xb') as log:
        child=subprocess.Popen([sys.executable,'-B','-u',str(root/'run_yuyv_video.py'),'--run'],cwd=root,
            stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        PENDING_CHILDREN.append(child);write_new(root/'child.json',{'pid':child.pid})
        deadline=time.monotonic()+120;position=0;cancelled=False
        def show_new():
            nonlocal position
            with (root/'camera.log').open('rb') as source:
                source.seek(position);data=source.read();position=source.tell()
            if data:print(data.decode('utf-8',errors='replace'),end='',flush=True)
        try:
            while child.poll() is None and time.monotonic()<deadline:
                try:child.wait(timeout=1)
                except subprocess.TimeoutExpired:pass
                show_new()
        except KeyboardInterrupt:cancelled=True
        if child.poll() is None:
            if not (root/'stop.request').exists():write_new(root/'stop.request',{'reason':'interrupted' if cancelled else 'outer_wait_timeout'})
            try:child.wait(timeout=10)
            except subprocess.TimeoutExpired:pass
        show_new()
        status={'pid':child.pid,'worker_exited':child.poll() is not None,'exitcode':child.poll(),
                'cleanup_unconfirmed':child.poll() is None,'archive_exists':(root/'yuyv-video-results.zip').is_file()}
        if status['worker_exited']:PENDING_CHILDREN.remove(child)
        else:print('收尾未确认；未强杀，不重试。保留此单元和目录。',flush=True)
    write_new(root/'launch-result.json',status)
    return status


if __name__=='__main__':
    parser=argparse.ArgumentParser();mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-bundle',action='store_true');mode.add_argument('--run',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parent
    if args.check_bundle:
        verify_package(root);print(json.dumps({'bundle_validated':True,'hardware_loaded':False}));raise SystemExit(0)
    raise SystemExit(worker(root))
