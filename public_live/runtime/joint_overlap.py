"""Start the unchanged pure-PS bridge once; explicitly transfer or dispose it."""
import os
import threading
import time

if __package__:
    from .joint_startup import replace_attribute
else:
    from joint_startup import replace_attribute


def describe(exc):return dict(type=type(exc).__name__,message=str(exc))


class ClaimTrace:
    """The frozen two-claim interval now measures adoption, not full warmup."""
    def __init__(self,trace):self.trace=trace
    def record(self,phase,*args,**kwargs):
        return self.trace.record('session_ready_bridge_wait' if phase=='ps_warmup' else phase,*args,**kwargs)
    def check(self,*args,**kwargs):return self.trace.check(*args,**kwargs)
    def call(self,*args,**kwargs):return self.trace.call(*args,**kwargs)


class Warmup:
    def __init__(self,bridge_type,trace,expected_identity):
        self.bridge_type,self.trace,self.expected=bridge_type,trace,dict(expected_identity)
        self.bridge=self.thread=None;self.done=threading.Event();self.abort=threading.Event()
        self.attempted=self.constructor_completed=self.ready_verified=self.session_attached=False
        self.bridge_created=self.claims=0;self.ready_info={};self.error=self.cleanup_error=None
        self.untransferred_closed=self.disposed=False

    def start(self):
        if self.attempted:raise RuntimeError('PS预热只能尝试一次')
        self.attempted=True;self.trace.check('before_parallel_ps_warmup')
        self.thread=threading.Thread(target=self._run,name='joint-pure-ps-warmup',daemon=False)
        self.thread.start()

    def _run(self):
        try:
            # If Thread.start was interrupted before this target entered, a
            # disposing caller can still forbid any late resource construction.
            if self.abort.is_set():return
            def construct():
                self.bridge=self.bridge_type.__new__(self.bridge_type);self.bridge_created+=1
                self.bridge_type.__init__(self.bridge,'pl_mmio')
                self.constructor_completed=True;self.ready_info=dict(self.bridge.info())
                self._validate_ready();self.ready_verified=True
            self.trace.call('ps_warmup',construct)
        except BaseException as exc:self.error=describe(exc)
        finally:self.done.set()

    def _validate_ready(self):
        b=self.bridge;r=self.ready_info;worker=getattr(b,'_worker',None)
        if (b is None or b.source!='pl_mmio' or b.backend is not None or b._initialized or b._closed or
            worker is None or not worker.is_alive() or type(r.get('worker_pid')) is not int or
            r['worker_pid'] in (0,os.getpid()) or r['worker_pid']!=worker.pid or
            r.get('worker_hardware_imported') is not False or (r.get('warmup_raw'),r.get('warmup_slots'))!=(700,700) or
            r.get('completed_steps')!=0 or r.get('pl_requests')!=0 or r.get('forced_termination') is not False or
            r.get('exitcode') is not None or any(r.get(k)!=v for k,v in self.expected.items())):
            raise RuntimeError('原PS ready身份/700点/空后端或零计数不符')

    def take(self,source):
        if source!='pl_mmio' or not self.attempted or self.thread is None or self.claims or self.disposed:
            raise RuntimeError('PS桥来源不符、未启动或已领取／关闭')
        self.trace.check('before_ps_ready_adoption')
        while not self.done.wait(.02):self.trace.check('waiting_for_ps_ready')
        self.thread.join();self.trace.check('after_parallel_ps_warmup')
        if self.error:raise RuntimeError('PS预热失败：'+self.error['message'])
        self._validate_ready()
        self.trace.record('ps_bridge_adopt','stage',worker_pid=self.ready_info['worker_pid'],source=source)
        self.claims+=1;return self.bridge

    def dispose(self,session):
        if self.disposed:return
        self.abort.set()
        if self.thread is not None and self.thread.ident is not None:
            # A Notebook interrupt must not unwind the entry hooks while the
            # constructor can still start a child or publish a bridge.
            while not self.done.is_set():
                try:self.done.wait(.05)
                except BaseException as exc:self.cleanup_error=self.cleanup_error or describe(exc)
            while True:
                try:self.thread.join();break
                except BaseException as exc:self.cleanup_error=self.cleanup_error or describe(exc)
        b=self.bridge;self.session_attached=bool(b is not None and getattr(session,'_process_chain',None) is b)
        if b is not None and not self.session_attached:
            try:
                if hasattr(b,'_connection') and not getattr(b,'_closed',False):
                    if hasattr(b,'_worker'):b.close()
                    else:b._connection.close();b._closed=True
            except BaseException as exc:self.cleanup_error=self.cleanup_error or describe(exc)
            finally:
                worker=getattr(b,'_worker',None);notice=time.monotonic()
                while worker is not None and worker.is_alive():
                    # The original constructor/close alone owns its original
                    # termination policy. This backstop never retries close/kill.
                    try:worker.join(.05)
                    except BaseException as exc:self.cleanup_error=self.cleanup_error or describe(exc)
                    if time.monotonic()-notice>=5:
                        try:print('等待未移交PS退出；保留所有者和引用，不增加强杀或重试。',flush=True)
                        except BaseException:pass
                        notice=time.monotonic()
            self.untransferred_closed=bool(getattr(b,'_closed',False))
        self.disposed=True

    def report(self):
        b=self.bridge;worker=getattr(b,'_worker',None);final=None;info_error=None
        if worker is not None:
            try:final=b.info()
            except BaseException as exc:info_error=describe(exc)
        thread_alive=bool(self.thread and self.thread.is_alive());child_alive=bool(worker and worker.is_alive())
        closed=bool(b is None or not hasattr(b,'_connection') or getattr(b,'_closed',False))
        return dict(schema='v3b25_overlap_owner_v1',owner_pid=os.getpid(),source='pl_mmio',
            attempted=self.attempted,bridge_created=self.bridge_created,claims=self.claims,
            constructor_completed=self.constructor_completed,ready_verified=self.ready_verified,
            ready_info=self.ready_info,expected_identity=self.expected,error=self.error,cleanup_error=self.cleanup_error,
            disposed=self.disposed,session_attached=self.session_attached,untransferred_closed=self.untransferred_closed,
            thread_alive=thread_alive,ps_child_alive=child_alive,final_info=final,final_info_error=info_error,
            cleanup_complete=bool(self.disposed and not thread_alive and not child_alive and closed and not self.cleanup_error),
            startup_speed_improved_verified=False)


def install_session(session,module,warmup):
    if getattr(session,'_overlap_session_installed',False):raise RuntimeError('ready bridge factory already installed')
    session._overlap_session_installed=True;start=session.start
    def adopted_start():
        with replace_attribute(module,'Bridge25',warmup.take):return start()
    session.start=adopted_start
