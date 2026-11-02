"""Frozen six-confirmation replay. No hardware, new worker, or algorithm copy."""
from contextlib import contextmanager
import cProfile
from dataclasses import asdict
import hashlib
import io
import json
import math
from pathlib import Path
import pstats
import sys
import time
from types import SimpleNamespace as N

if __package__:from .ps_budget_guard import differences
else:from ps_budget_guard import differences


@contextmanager
def no_hardware():
    if any(n=='pynq' or n.startswith('pynq.') for n in sys.modules):raise RuntimeError('hardware module already imported')
    class Block:
        def find_spec(self,fullname,path=None,target=None):
            if fullname=='pynq' or fullname.startswith('pynq.'):raise RuntimeError('hardware import forbidden in read-only replay')
    block=Block();sys.meta_path.insert(0,block)
    try:yield
    finally:sys.meta_path.remove(block)


def load_runtime(frozen):
    frozen=Path(frozen).resolve();sys.path.insert(0,str(frozen))
    from entry25_guard import validate,activate,identity
    validate(frozen);activate(frozen)
    from effective25.identity import bootstrap
    bootstrap(frozen/'base',algorithm=True)
    from effective25.frontend import Frontend25
    from effective25 import bridge
    from entry25_candidate import DelayedPeakChain
    from entry25_worker import worker
    from heart_v3a.runtime_backend import FixedNlmsBackend
    from heart_v3a.live.contracts import LiveRecord
    return N(Chain=DelayedPeakChain,Frontend=Frontend25,Fixed=FixedNlmsBackend,Bridge=bridge.Bridge25,
        bridge_module=bridge,worker=worker,LiveRecord=LiveRecord,identity=identity(frozen))


def observations(deps,rows):
    result=[]
    for original in rows:
        r=dict(original);r['sequence']=int(r['sequence']);r['time_s']=float(r['time_s']);r['ir_raw']=float(r['ir_raw'])
        for k in ('pair_ok','accel_valid','pl_fifo_ok'):
            if r[k]=='' and k=='pl_fifo_ok':continue
            if r[k] not in ('True','False'):raise ValueError('raw boolean not explicit: '+k)
            r[k]=r[k]=='True'
        if r['pair_ok']:
            for k in ('ax_g','ay_g','az_g'):r[k]=float(r[k])
        result.append(deps.LiveRecord(r,int(r['ppg_read_completed_ns'])).to_observation())
    return result


def values(slot,runtime):
    result=asdict(runtime);result.update(result.pop('frame'))
    support=slot.support_sequences or (None,None);times=slot.support_times or (None,None)
    result.update(source_first=slot.source_sequences[0],source_last=slot.source_sequences[1],
        source_first_time_s=slot.source_times[0],source_last_time_s=slot.source_times[1],
        available_time_s=slot.available_time_s,signal_time_s=slot.signal_time_s,
        support_first=support[0],support_last=support[1],support_first_time_s=times[0],support_last_time_s=times[1],
        generation=slot.generation,slot_valid=slot.valid,slot_contact_ready=slot.contact_ready,slot_reason=slot.reason)
    return result


def base_report():
    return dict(count=0,difference_count=0,first_differences=[],samples=[],error=None,cleanup_complete=True)


def accumulate(report,reference,slot,runtime,hasher):
    actual=values(slot,runtime);delta=differences(reference,actual)
    report['count']+=1;report['difference_count']+=len(delta)
    report['first_differences'].extend(delta[:max(0,16-len(report['first_differences']))])
    hasher.update(json.dumps(actual,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n')


def verify_records(deps,obs,rows,*,emit=print):
    if len(obs)!=len(rows):raise ValueError('reference input count mismatch')
    report=base_report();front=deps.Frontend();chain=deps.Chain(deps.Fixed());h=hashlib.sha256()
    for i,(ob,row) in enumerate(zip(obs,rows)):
        slot=front.push(ob);accumulate(report,row,slot,chain.step(slot),h)
        if (i+1)%250==0:emit('初核 %d/%d 点'%(i+1,len(rows)),flush=True)
    report.update(runtime_sha256=h.hexdigest(),frontend=front.audit());return report


def warmup(deps):
    began=time.perf_counter_ns();front=deps.Frontend();chain=deps.Chain(deps.Fixed())
    from heart_v2.runtime_main_chain import Observation
    for i in range(700):
        chain.step(front.push(Observation(i,i/25.,125000+600*math.sin(2*math.pi*1.2*i/25.),(0.,0.,1.),True)))
    return (time.perf_counter_ns()-began)/1e9


class SoftwareBackend:
    source='python_fixed'
    def __init__(self,backend):self.backend=backend;self.wall=self.cpu=0
    def reset(self):return self.backend.reset()
    def transact(self,packet):
        wall=time.perf_counter_ns();cpu=time.process_time_ns()
        try:return self.backend.transact(packet)
        finally:self.cpu=time.process_time_ns()-cpu;self.wall=time.perf_counter_ns()-wall


def timed_rows(deps,obs,rows,chain,front,backend,report,emit):
    h=hashlib.sha256()
    try:
        for i,(ob,row) in enumerate(zip(obs,rows)):
            w0=time.perf_counter_ns();c0=time.process_time_ns()
            slot=front.push(ob);w1=time.perf_counter_ns();c1=time.process_time_ns()
            runtime=chain.step(slot);c2=time.process_time_ns();w2=time.perf_counter_ns()
            report['samples'].append(dict(sequence=ob.sequence,front_wall_ns=w1-w0,step_wall_ns=w2-w1,
                total_wall_ns=w2-w0,front_caller_cpu_ns=c1-c0,step_caller_cpu_ns=c2-c1,
                total_caller_cpu_ns=c2-c0,software_nlms_wall_ns=backend.wall,software_nlms_caller_cpu_ns=backend.cpu))
            accumulate(report,row,slot,runtime,h)
            if (i+1)%250==0:emit('已计时 %d/%d 点'%(i+1,len(rows)),flush=True)
    finally:report.update(runtime_sha256=h.hexdigest(),frontend=front.audit())


def run_direct(deps,obs,rows,*,emit=print):
    report=base_report();report.update(warmup_slots=700,warmup_seconds=warmup(deps),ordinary_timing=True,
        cpu_scope='this analysis process including any library threads; not a hardware-owner CPU measurement')
    backend=SoftwareBackend(deps.Fixed());front=deps.Frontend();chain=deps.Chain(backend)
    try:timed_rows(deps,obs,rows,chain,front,backend,report,emit)
    except BaseException as exc:report['error']=dict(stage='direct',type=type(exc).__name__,message=str(exc))
    return report


def finish_bridge(bridge,report,*,emit=print):
    def failed(exc):
        report['error']=report['error'] or dict(stage='ipc_cleanup',type=type(exc).__name__,message=str(exc))
    worker=getattr(bridge,'_worker',None)
    try:
        if not getattr(bridge,'_closed',False):
            if worker is not None:bridge.close()
            elif hasattr(bridge,'_connection'):bridge._connection.close();bridge._closed=True
    except BaseException as exc:failed(exc)
    finally:
        notice=time.monotonic()
        while worker is not None and worker.is_alive():
            try:worker.join(.05)
            except BaseException as exc:failed(exc)
            if time.monotonic()-notice>=5:
                try:emit('保留原PS桥并等待退出；不重复close或增加强杀。',flush=True)
                except BaseException:pass
                notice=time.monotonic()
        if not getattr(bridge,'_closed',False) and hasattr(bridge,'_connection'):
            try:bridge._connection.close();bridge._closed=True
            except BaseException as exc:failed(exc)
        report['cleanup_complete']=bool((worker is None or not worker.is_alive()) and
            (not hasattr(bridge,'_connection') or getattr(bridge,'_closed',False)))
        if worker is not None:
            try:
                report['isolation']=bridge.info()
                if report['isolation']['forced_termination'] or report['isolation']['exitcode']!=0:
                    failed(RuntimeError('original PS process did not exit naturally'))
            except BaseException as exc:failed(exc)


def run_ipc(deps,obs,rows,*,emit=print):
    report=base_report();report.update(ordinary_timing=True,warmup_slots=700,
        cpu_scope='caller process only, NOT the PS child CPU; software NLMS runs in caller',isolation=None)
    original=deps.bridge_module.worker;bridge=None
    try:
        deps.bridge_module.worker=deps.worker
        bridge=deps.Bridge.__new__(deps.Bridge);deps.Bridge.__init__(bridge,'python_fixed')
        ready=bridge.info();report['ready_info']=dict(ready)
        if (any(ready.get(k)!=v for k,v in deps.identity.items()) or
            (ready.get('warmup_raw'),ready.get('warmup_slots'))!=(700,700) or
            ready.get('worker_hardware_imported') is not False or ready.get('forced_termination') is not False or
            ready.get('exitcode') is not None or ready.get('completed_steps')!=0 or ready.get('pl_requests')!=0):
            raise RuntimeError('original six-confirmation/700-point ready identity changed')
        backend=SoftwareBackend(deps.Fixed());bridge.attach_backend(backend);bridge.reset()
        timed_rows(deps,obs,rows,bridge,deps.Frontend(),backend,report,emit)
    except BaseException as exc:report['error']=dict(stage='ipc',type=type(exc).__name__,message=str(exc))
    finally:
        try:
            if bridge is not None:finish_bridge(bridge,report,emit=emit)
        finally:deps.bridge_module.worker=original
    return report


def profile_direct(deps,obs,rows,*,emit=print):
    report=base_report();report.update(ordinary_timing=False,warmup_slots=700,warmup_seconds=warmup(deps))
    chain=deps.Chain(deps.Fixed());front=deps.Frontend();profiler=cProfile.Profile();h=hashlib.sha256()
    try:
        for i,(ob,row) in enumerate(zip(obs,rows)):
            profiler.enable()
            try:slot=front.push(ob);runtime=chain.step(slot)
            finally:profiler.disable()
            accumulate(report,row,slot,runtime,h)
            if (i+1)%250==0:emit('已剖析 %d/%d 点'%(i+1,len(rows)),flush=True)
    except BaseException as exc:report['error']=dict(stage='profile',type=type(exc).__name__,message=str(exc))
    finally:
        stream=io.StringIO();pstats.Stats(profiler,stream=stream).sort_stats('cumulative').print_stats(35)
        report.update(text=stream.getvalue(),runtime_sha256=h.hexdigest(),frontend=front.audit())
    return report
