"""Bounded per-caller observation. No algorithm/device imports or new I/O."""
from array import array
import os
import threading
import time

CAPACITIES=dict(read_batch=4096,step=4096,snapshot=8192,publish=8192,
    grab=4096,retrieve=512,frame=512,vision=512)
FIELDS=('call_index','source_sequence','begin_ns','end_ns','thread_cpu_ns','thread_id','returned','aux')

class Probe:
    def __init__(self,*,clock_ns=time.monotonic_ns,cpu_ns=None,capacities=None):
        self.clock_ns=clock_ns;self.cpu_ns=cpu_ns or getattr(time,'thread_time_ns',None)
        if not callable(self.cpu_ns):raise RuntimeError('thread_time_ns unavailable; no hardware started')
        self.clock_ns();self.cpu_ns()
        sizes=dict(CAPACITIES);sizes.update(capacities or {})
        self.streams={n:dict(buffer=array('q',[0])*(8*c),capacity=c,calls=0,stored=0,
            dropped=0,error=None,thread_id=None,active=0) for n,c in sizes.items()}
        if any(s['buffer'].itemsize!=8 for s in self.streams.values()):raise RuntimeError('signed64 storage required')
        self.payload_bytes=sum(len(s['buffer'])*8 for s in self.streams.values())
        self.hooks=[];self.installed=False;self.restored=False;self.install_error=None

    def _failed(self,s,exc):
        if s['error'] is None:s['error']=dict(type=type(exc).__name__,message=str(exc)[:256])

    def call(self,name,operation,*,token=-1,aux=0,after=None):
        s=self.streams[name];index=s['calls'];s['calls']+=1;s['active']+=1
        record=False;returned=0;value=None
        try:
            try:
                if s['error']:raise RuntimeError('observation already incomplete')
                if s['stored']>=s['capacity']:raise OverflowError('bounded observation stream full')
                tid=threading.get_native_id()
                if s['thread_id'] is None:s['thread_id']=tid
                if tid!=s['thread_id']:raise RuntimeError('observation stream has multiple callers')
                w0=self.clock_ns();c0=self.cpu_ns();record=True
            except BaseException as exc:self._failed(s,exc)
            value=operation();returned=1
            return value
        finally:
            try:
                if record:
                    c1=self.cpu_ns();w1=self.clock_ns()
                    if any(type(v) is not int for v in (w0,w1,c0,c1)) or min(w0,c0,w1-w0,c1-c0)<0:
                        raise ValueError('boundary clocks invalid')
                    if after is not None and returned:token,aux=after(value)
                    values=(index,int(token),w0,w1,c1-c0,tid,returned,int(aux))
                    offset=s['stored']*8
                    for i,v in enumerate(values):s['buffer'][offset+i]=v
                    s['stored']+=1
                else:s['dropped']+=1
            except BaseException as exc:
                self._failed(s,exc);s['dropped']+=1
            finally:s['active']-=1

    def replace(self,obj,name,value):
        present=name in vars(obj);original=getattr(obj,name)
        self.hooks.append((obj,name,original,present));setattr(obj,name,value)

    def wrap(self,obj,method,stream,*,before=None,after=None):
        original=getattr(obj,method)
        def wrapped(*args,**kwargs):
            token,aux=-1,0
            if before is not None:
                try:token,aux=before(args,kwargs)
                except BaseException as exc:self._failed(self.streams[stream],exc)
            return self.call(stream,lambda:original(*args,**kwargs),token=token,aux=aux,after=after)
        self.replace(obj,method,wrapped)

    def install(self,session,video,mailbox):
        if self.installed:raise RuntimeError('boundary hooks already installed')
        self.installed=True
        def batch(value):
            rows=value.records
            return (rows[0].raw['sequence'] if rows else -1,len(rows))
        def snapshot(value):
            return (value.latest.runtime.frame.sequence if value.latest else -1,len(value.history))
        self.wrap(session.source,'read_batch','read_batch',after=batch)
        self.wrap(session,'snapshot','snapshot',after=snapshot)
        self.wrap(mailbox,'publish','publish',before=lambda a,k:snapshot(a[0]))
        create=session._create_processing_chain;bridges=[]
        def created(*args,**kwargs):
            chain=create(*args,**kwargs)
            if not bridges:
                bridges.append(chain)
                try:self.wrap(chain,'step','step',before=lambda a,k:(a[0].source_sequences[0],0))
                except BaseException as exc:self._failed(self.streams['step'],exc)
            elif chain is not bridges[0]:self._failed(self.streams['step'],RuntimeError('original processing bridge identity changed'))
            return chain
        self.replace(session,'_create_processing_chain',created)
        self.wrap(video,'process_ready_frame','frame',before=lambda a,k:(k['sequence'],0))
        self.wrap(video.port,'process','vision',before=lambda a,k:(k['sequence'],0))
        raw=video.camera;probe=self
        class Camera:
            def __getattr__(self,name):return getattr(raw,name)
            def grab(self,*a,**k):return probe.call('grab',lambda:raw.grab(*a,**k))
            def retrieve(self,*a,**k):return probe.call('retrieve',lambda:raw.retrieve(*a,**k))
        self.replace(video,'camera',Camera())

    def restore(self):
        if any(s['active'] for s in self.streams.values()):raise RuntimeError('boundary callers still active; retain hooks')
        while self.hooks:
            obj,name,original,present=self.hooks.pop()
            if present:setattr(obj,name,original)
            else:delattr(obj,name)
        self.restored=True

    def report(self):
        if any(s['active'] for s in self.streams.values()):raise RuntimeError('cannot export active boundary calls')
        return dict(schema='v3b25_owner_boundaries_v1',owner_pid=os.getpid(),fields=list(FIELDS),
            payload_bytes=self.payload_bytes,hooks_installed=self.installed,hooks_restored=self.restored,install_error=self.install_error,
            clocks=dict(wall='monotonic_ns',cpu='thread_time_ns'),
            scope='caller thread CPU only; no PS child/library-worker CPU; nested/concurrent walls are not additive; observation perturbs scheduling',
            streams={n:dict(capacity=s['capacity'],calls=s['calls'],stored=s['stored'],dropped=s['dropped'],
                error=s['error'],thread_id=s['thread_id'],rows=[list(s['buffer'][i*8:(i+1)*8]) for i in range(s['stored'])])
                for n,s in self.streams.items()})
