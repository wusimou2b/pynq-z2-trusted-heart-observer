"""Startup-only timing and visible-stop gates; no hardware imports at load time."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import threading
import time


class StartupCancelled(RuntimeError):pass


@contextmanager
def replace_attribute(target,name,value):
    original=getattr(target,name);setattr(target,name,value)
    try:yield
    finally:setattr(target,name,original)


class StartupTrace:
    def __init__(self,directory,stop,*,clock_ns=time.monotonic_ns,emit=print):
        self.directory=Path(directory);self.stop=stop;self.clock_ns=clock_ns;self.emit=emit
        self.path=self.directory/'startup_events.jsonl'
        self.stream=self.path.open('x',encoding='utf-8')
        self.lock=threading.RLock();self.events=[];self.cancelled=None;self._finished=None
        self.started_ns=self.clock_ns();self.record('worker','entry')

    def record(self,phase,kind,**details):
        with self.lock:
            now=self.clock_ns()
            if type(now) is not int or now<self.started_ns or self.events and now<self.events[-1]['at_ns']:
                raise ValueError('startup trace clock is not monotonic integer ns')
            row=dict(index=len(self.events),phase=phase,kind=kind,at_ns=now,owner_pid=os.getpid(),
                stop_requested=bool(self.stop.is_set()),details=details)
            self.stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');self.stream.flush()
            self.events.append(row)
            if kind in ('begin','stage','cancelled'):
                try:self.emit('STARTUP %.3fs %s %s'%((now-self.started_ns)/1e9,phase,kind),flush=True)
                except BaseException:pass
            return row

    def check(self,phase):
        if self.stop.is_set():
            row=self.record(phase,'cancelled')
            if self.cancelled is None:self.cancelled=dict(phase=phase,at_ns=row['at_ns'])
            raise StartupCancelled('父停止请求已到达，取消后续启动阶段：'+phase)

    def call(self,phase,operation,*,cancellable=True):
        self.record(phase,'begin')
        try:
            if cancellable:self.check(phase)
            result=operation()
        except BaseException as exc:
            self.record(phase,'error',type=type(exc).__name__,message=str(exc));raise
        self.record(phase,'end');return result

    def finish(self,**details):
        if self._finished is not None:return self._finished
        try:last=self.record('worker','finish',**details)
        finally:self.stream.close()
        stacks={};intervals=[]
        for row in self.events:
            name=row['phase'];kind=row['kind']
            if kind=='begin':stacks.setdefault(name,[]).append(row)
            elif kind in ('end','error') and stacks.get(name):
                began=stacks[name].pop();intervals.append(dict(phase=name,begin_index=began['index'],
                    end_index=row['index'],outcome=kind,elapsed_ns=row['at_ns']-began['at_ns']))
        report=dict(schema='v3b25_owner_startup_v1',scope='owner lifecycle wall time; nested phases are not additive',
            owner_pid=os.getpid(),started_ns=self.started_ns,finished_ns=last['at_ns'],
            elapsed_ns=last['at_ns']-self.started_ns,events_count=len(self.events),cancelled=self.cancelled,
            phase_intervals=intervals,unpaired_begins=[r['index'] for rows in stacks.values() for r in rows],
            events_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),trace_closed=True,
            startup_speed_improved_verified=False,details=details)
        with (self.directory/'owner_startup.json').open('x',encoding='utf-8') as f:
            json.dump(report,f,ensure_ascii=False,indent=2,allow_nan=False)
        self._finished=report;return report


def guard_session(session,trace):
    if getattr(session,'_joint_startup_guard_installed',False):raise RuntimeError('startup guard already installed')
    session._joint_startup_guard_installed=True
    original_start=session.start;original_claim=session._claim_owner;original_begin=session.source.begin
    claims=0
    def claim():
        nonlocal claims
        claims+=1
        if claims==1:
            trace.check('before_ps_warmup');result=original_claim();trace.record('ps_warmup','begin');return result
        if claims==2:
            trace.record('ps_warmup','end');trace.check('after_ps_warmup_before_threads')
        return original_claim()
    def begin():
        result=trace.call('source_begin',original_begin)
        trace.record('formal_epoch','observed',started_ns=result['started_ns'])
        return result
    session._claim_owner=claim;session.source.begin=begin
    session.start=lambda:trace.call('heart_start',original_start)


def instrument_binding(binding,trace):
    if __package__:
        from . import joint_concurrent_binding as concurrent
        from .joint_heart_binding import JointBinding
        from .joint_shared_video import SharedVideoResources
    else:
        import joint_concurrent_binding as concurrent
        from joint_heart_binding import JointBinding
        from joint_shared_video import SharedVideoResources
    if getattr(binding,'_startup_instrumented',False):raise RuntimeError('binding already instrumented')
    binding._startup_instrumented=True
    api_factory,owner_factory,prepare=binding.api_factory,binding.owner_factory,binding.prepare
    binding.api_factory=lambda:trace.call('video_driver_imports',api_factory)
    def make_owner(*args,**kwargs):
        owner=owner_factory(*args,**kwargs);opened=owner.open
        owner.open=lambda:trace.call('joint_open',opened)
        return owner
    binding.owner_factory=make_owner
    def timed_prepare(*args,**kwargs):
        trace.check('before_prepare')
        original_heart=JointBinding.prepare;original_pack=concurrent.packing_preflight;original_video=SharedVideoResources.open
        def heart(self,*a,**k):
            if self is not binding:return original_heart(self,*a,**k)
            return trace.call('heart_sensor_prepare',lambda:original_heart(self,*a,**k))
        def packing(*a,**k):return trace.call('packing_preflight',lambda:original_pack(*a,**k))
        def video(self,*a,**k):
            if self.owner is not binding.owner:return original_video(self,*a,**k)
            stage=self._stage
            def staged(name):
                trace.record(name,'stage');trace.check(name);return stage(name)
            self._stage=staged
            try:return trace.call('video_setup',lambda:original_video(self,*a,**k))
            finally:self._stage=stage
        with replace_attribute(JointBinding,'prepare',heart),replace_attribute(concurrent,'packing_preflight',packing),\
                replace_attribute(SharedVideoResources,'open',video):
            session=trace.call('joint_prepare',lambda:prepare(*args,**kwargs))
        guard_session(session,trace)
        start_video=binding.video_runner.start
        binding.video_runner.start=lambda:trace.call('video_drain_thread_start',start_video)
        return session
    binding.prepare=timed_prepare
    return binding
