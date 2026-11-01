"""Disposable preview coordinator: the Notebook never constructs PL drivers."""
import json
import os
from pathlib import Path
import threading
import time

if __package__:from .video_split_process import SharedJSON
else:from video_split_process import SharedJSON


class PreviewControl:
    def __init__(self,ctx,directory):
        self.directory=str(directory)
        self.stop,self.ready,self.saved,self.quarantined=(ctx.Event() for _ in range(4))
        self.formal_started_ns=ctx.Value('q',0);self.failure=SharedJSON(ctx)
    def mark_ready(self,epoch):self.formal_started_ns.value=epoch;self.ready.set()
    def store_result(self,result):
        with (Path(self.directory)/'result.json').open('x',encoding='utf-8') as sink:
            json.dump(result,sink,ensure_ascii=False,indent=2,allow_nan=False)
        if result.get('cleanup_complete') is not True:self.quarantined.set()
        self.saved.set()


def verify_spec(spec):
    if __package__:from .video_split_guard import verify
    else:from video_split_guard import verify
    verify(spec['root'],spec['manifest_sha256'])


def owned_handler(spec,control):
    if __package__:from . import run_video_split as entry
    else:import run_video_split as entry
    if Path(entry.ROOT).resolve()!=Path(spec['root']).resolve():raise ValueError('mixed preview owner root')
    return entry._run_owned_preview20(expected_manifest_sha256=spec['manifest_sha256'],control=control,
        startup_deadline_ns=spec['startup_deadline_ns'])


def preview_worker(spec,control,verify,handler):
    try:verify(spec)
    except BaseException as exc:
        control.store_result(dict(error=dict(type=type(exc).__name__,message=str(exc)),cleanup_error=None,
            cleanup_complete=True,no_owner_constructed=True,ownership_qualification_passed=False))
        return
    try:
        result=handler(spec,control)
        if not control.saved.is_set():control.store_result(result)
    except BaseException as exc:
        # Keep the traceback (and any owner/resource references in it) alive
        # while the actual resource state is unknown. Never kill this process.
        control.failure.write(dict(type=type(exc).__name__,message=str(exc)[:4096]))
        if not control.saved.is_set():
            control.store_result(dict(error=control.failure.read(),cleanup_error=None,
                cleanup_complete=False,ownership_qualification_passed=False,resource_state='unknown_after_owner_exception'))
        control.quarantined.set()
        threading.Event().wait()


class PreviewSession:
    def __init__(self,ctx,spec,*,verify=verify_spec,handler=owned_handler):
        self.ctx,self.spec,self.verify,self.handler=ctx,dict(spec),verify,handler
        self.control=PreviewControl(ctx,spec['directory']);self.process=None
    def start(self):
        if self.process is not None:raise RuntimeError('preview owner already attempted; no retry')
        self.process=self.ctx.Process(target=preview_worker,args=(self.spec,self.control,self.verify,self.handler),
            name='video-preview-global-pl-owner',daemon=False)
        self.process.start()
    def request_stop(self):self.control.stop.set()
    def wait(self,*,emit=print):
        announced=False;deadline_sent=False
        while not self.control.saved.wait(.05):
            if self.control.ready.is_set() and not announced:
                emit('READY：20秒动态视频已开始；请观察屏幕与序号。',flush=True);announced=True
            if not self.control.ready.is_set() and time.monotonic_ns()>=self.spec.get('startup_deadline_ns',2**63-1):
                self.request_stop()
                if not deadline_sent:emit('已到300秒启动边界，等待所有者正常收尾；不强杀。',flush=True);deadline_sent=True
            if not self.process.is_alive():
                self.process.join()
                return dict(error=dict(type='OwnerExited',message='owner exited before saved result'),cleanup_complete=False,
                    ownership_qualification_passed=False,coordinator=dict(pid=self.process.pid,exitcode=self.process.exitcode,
                        alive=False,retained=False,natural_exit=False))
        raw=json.loads((Path(self.control.directory)/'result.json').read_bytes())
        if self.control.quarantined.is_set():
            return dict(raw,coordinator=dict(pid=self.process.pid,exitcode=self.process.exitcode,
                alive=self.process.is_alive(),retained=True,natural_exit=False))
        notice=time.monotonic()
        while self.process.is_alive():
            if self.control.quarantined.is_set():
                return dict(raw,coordinator=dict(pid=self.process.pid,exitcode=self.process.exitcode,
                    alive=True,retained=True,natural_exit=False,error=self.control.failure.read()))
            self.process.join(.1)
            if time.monotonic()-notice>=5:
                emit('资源已收尾，等待硬件所有者进程自然退出并解除全部映射。',flush=True);notice=time.monotonic()
        return dict(raw,coordinator=dict(pid=self.process.pid,exitcode=self.process.exitcode,
            alive=False,retained=False,natural_exit=self.process.exitcode==0))
