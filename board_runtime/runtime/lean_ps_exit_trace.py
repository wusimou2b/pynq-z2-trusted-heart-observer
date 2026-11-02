"""Bounded exit observers: never own GC, process waits, signals or cleanup."""
import atexit
import gc
import multiprocessing as mp
import os
import threading
import time

CAPACITY=64
COLUMNS=('event','at_ns','thread_cpu_ns','process_cpu_ns','detail')
EVENTS=('close_begin','close_end','close_error','join_begin','join_end','join_error',
        'alive_result','alive_error','terminate_begin','terminate_end','terminate_error',
        'delegate_returned','delegate_error','mp_exit_begin','mp_exit_end','mp_exit_error',
        'threads_begin','threads_end','threads_error','flush_begin','flush_end','flush_error',
        'atexit_enter','gc_begin','gc_end')


def make_shared():
    ctx=mp.get_context('spawn');result={}
    for side in ('parent','child'):
        result[side]=dict(rows=ctx.RawArray('q',CAPACITY*len(COLUMNS)))
        for key in ('count','errors','ignored_nonmain','pid'):
            result[side][key]=ctx.RawValue('q',0)
    return result


class Trace:
    def __init__(self,shared,side):
        self.data=shared[side];self.events={name:i for i,name in enumerate(EVENTS)}
        self.wall=time.monotonic_ns;self.thread_cpu=time.thread_time_ns;self.process_cpu=time.process_time_ns
        self.ident=threading.get_ident;self.main_ident=self.ident();self.data['pid'].value=os.getpid()
    def error(self):
        try:self.data['errors'].value+=1
        except Exception:pass
    def event(self,name,detail=0):
        try:
            if self.ident()!=self.main_ident:
                self.data['ignored_nonmain'].value+=1;return
            i=self.data['count'].value
            if not 0<=i<CAPACITY:raise ValueError('exit trace full')
            values=(self.events[name],self.wall(),self.thread_cpu(),self.process_cpu(),detail)
            for j,v in enumerate(values):self.data['rows'][i*len(COLUMNS)+j]=v
            self.data['count'].value=i+1
        except Exception:self.error()
    def wrap(self,name,original,*,detail=None):
        def call(*args,**kwargs):
            value=0
            if detail is not None:
                try:value=detail(args,kwargs)
                except Exception:self.error();value=-2
            self.event(name+'_begin',value)
            try:result=original(*args,**kwargs)
            except BaseException:self.event(name+'_error',value);raise
            self.event(name+'_end',value);return result
        return call


def observe_close(original,bridge,trace,*args,**kwargs):
    changes=[];process=getattr(bridge,'_worker',None)
    def timeout(a,k):
        value=a[0] if a else k.get('timeout')
        return -1 if value is None else int(value*1_000_000_000)
    try:
        for name in ('join','is_alive','terminate'):
            try:
                method=getattr(process,name);had=name in vars(process);prior=vars(process).get(name)
                if name=='is_alive':
                    def alive(*a,_method=method,**k):
                        try:value=_method(*a,**k)
                        except BaseException:trace.event('alive_error');raise
                        try:trace.event('alive_result',int(value))
                        except Exception:trace.error()
                        return value
                    wrapped=alive
                else:wrapped=trace.wrap(name,method,detail=timeout if name=='join' else None)
                setattr(process,name,wrapped);changes.append((name,had,prior))
            except Exception:trace.error()
        return trace.wrap('close',lambda:original(bridge,*args,**kwargs))()
    finally:
        for name,had,prior in reversed(changes):
            try:
                if had:setattr(process,name,prior)
                else:delattr(process,name)
            except Exception:trace.error()


class ChildHooks:
    def __init__(self,trace):
        import multiprocessing.util as util
        self.trace=trace;self.previous=[];self.after=False;self.installed=False
        # Capture references now: interpreter globals may be clearing later.
        event=trace.event
        def at_exit():event('atexit_enter')
        def observed_gc(phase,info):
            try:
                if phase in ('start','stop'):event('gc_begin' if phase=='start' else 'gc_end',info.get('generation',-1))
            except Exception:trace.error()
        self.at_exit=at_exit;self.observed_gc=observed_gc
        self.register=atexit.register;self.unregister=atexit.unregister;self.callbacks=gc.callbacks
        try:
            for obj,key,label in ((util,'_exit_function','mp_exit'),(threading,'_shutdown','threads'),
                                  (util,'_flush_std_streams','flush')):
                old=getattr(obj,key);wrapped=trace.wrap(label,old)
                setattr(obj,key,wrapped);self.previous.append((obj,key,old,wrapped))
            self.installed=True
        except Exception:
            trace.error();self.restore()
    def after_delegate(self,*,success=True):
        self.trace.event('delegate_returned' if success else 'delegate_error')
        if self.after or not self.installed:return
        self.after=True
        try:self.register(self.at_exit)
        except Exception:self.trace.error()
        try:self.callbacks.append(self.observed_gc)
        except Exception:self.trace.error()
    def restore(self):
        """Withdraw a partial installation without changing original functions."""
        try:self.unregister(self.at_exit)
        except Exception:self.trace.error()
        if self.observed_gc in self.callbacks:self.callbacks.remove(self.observed_gc)
        for obj,key,old,wrapped in reversed(self.previous):
            try:
                if getattr(obj,key) is wrapped:setattr(obj,key,old)
            except Exception:self.trace.error()
        self.installed=False


def install_child(trace):return ChildHooks(trace)


def snapshot(shared,side):
    """Caller must prove original owner AND actual PS have exited first."""
    data=shared[side];count=data['count'].value
    if not 0<=count<=CAPACITY:raise ValueError('invalid exit trace count')
    rows=[]
    for i in range(count):
        row=dict(zip(COLUMNS,data['rows'][i*len(COLUMNS):(i+1)*len(COLUMNS)]))
        row['event']=EVENTS[row['event']];rows.append(row)
    return dict(rows=rows,errors=data['errors'].value,ignored_nonmain=data['ignored_nonmain'].value,
        pid=data['pid'].value,capacity=CAPACITY,bytes=len(data['rows'])*8)


def analyze(data):
    stacks={};intervals=[]
    for i,row in enumerate(data['rows']):
        event=row['event']
        if event.endswith('_begin'):stacks.setdefault((event[:-6],row['detail']),[]).append((i,row))
        elif event.endswith(('_end','_error')):
            error=event.endswith('_error');key=(event[:-6] if error else event[:-4],row['detail'])
            if stacks.get(key):
                index,began=stacks[key].pop()
                intervals.append(dict(phase=key[0],detail=key[1],begin_index=index,end_index=i,
                    status='error' if error else 'complete',wall_ns=row['at_ns']-began['at_ns'],
                    thread_cpu_ns=row['thread_cpu_ns']-began['thread_cpu_ns'],
                    process_cpu_ns=row['process_cpu_ns']-began['process_cpu_ns']))
    for key,items in stacks.items():
        for index,row in items:
            intervals.append(dict(phase=key[0],detail=key[1],begin_index=index,end_index=None,
                status='active_at_exit',wall_ns=None,thread_cpu_ns=None,process_cpu_ns=None))
    return dict(data,intervals=sorted(intervals,key=lambda p:p['begin_index']),
        last_event=data['rows'][-1]['event'] if data['rows'] else None,
        delegate_returned=any(r['event']=='delegate_returned' for r in data['rows']),
        atexit_entered=any(r['event']=='atexit_enter' for r in data['rows']))


def verify_runtime():
    """Cold pre-hardware check of THIS interpreter, not a copied stdlib guess."""
    import hashlib,inspect,json,sys
    import multiprocessing.process as process
    import multiprocessing.spawn as spawn
    import multiprocessing.util as util
    from pathlib import Path
    expected={'run','_exit_function','_shutdown','_flush_std_streams'}
    bootstrap=process.BaseProcess._bootstrap
    if sys.implementation.name!='cpython' or not expected.issubset(set(bootstrap.__code__.co_names)):
        raise RuntimeError('unsupported actual bootstrap exit path')
    if not {'_bootstrap'}.issubset(set(spawn._main.__code__.co_names)):
        raise RuntimeError('unsupported actual spawn bootstrap path')
    functions={}
    for name,fn in (('bootstrap',bootstrap),('mp_exit',util._exit_function),
                     ('threads',threading._shutdown),('flush',util._flush_std_streams)):
        if not callable(fn):raise RuntimeError('missing exit hook '+name)
        source=inspect.getsource(fn)
        functions[name]=dict(module=fn.__module__,qualname=fn.__qualname__,
            file=inspect.getsourcefile(fn),source_sha256=hashlib.sha256(source.encode()).hexdigest())
    files={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
        {process.__file__,spawn.__file__,util.__file__,threading.__file__}}
    return dict(schema='v3b25_ps_exit_runtime_v1',compatible=True,python=sys.version,
        implementation=sys.implementation.name,platform=sys.platform,functions=functions,stdlib_files=files)
