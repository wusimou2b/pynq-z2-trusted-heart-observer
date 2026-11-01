"""One outer round trip per sample; sole hardware ownership and all receipts retained.

The owner prepares the four reference DC values before its SAMPLE call. The PS
child independently recomputes them and checks exact bits before consuming the
receipt. No batching, speculative next sample, copied sensor sample or fallback.
"""
import struct
import time
from types import MethodType
if __package__:
    from . import main_heart_process as original
    from .main_heart_mmio import SampleRequest, SampleResult
    from .small_heart_model import Identity
else:
    import main_heart_process as original
    from main_heart_mmio import SampleRequest, SampleResult
    from small_heart_model import Identity

CONTROLS=dict(beta_int=32212255,update_enabled=True,bypass=False)
OriginalBridge=original.Bridge


def same_request(a,b):
    if not isinstance(a,SampleRequest) or not isinstance(b,SampleRequest):return False
    return a==b and struct.pack('<4d',*a.references)==struct.pack('<4d',*b.references)


class Preparation:
    def __init__(self,run_id):
        from v3a_rate25.policy import configuration
        self.run_id=run_id;self.config=configuration()['preprocess'];self.previous=None;self.refs=None

    def request(self,slot,rid,controls):
        import numpy as np
        from v3a_rate25.frontend import Slot
        from heart_v2.preprocess import CausalDcBlocker
        if controls!=CONTROLS:raise ValueError('main original25 controls differ')
        if not isinstance(slot,Slot):raise ValueError('必须为有原始来源的25Hz槽')
        prev=self.previous
        if slot.sequence!=(0 if prev is None else prev.sequence+1):raise ValueError('25Hz槽重复／缺失／倒退')
        if prev is not None and slot.available_time_s<=prev.available_time_s:raise ValueError('25Hz可用时刻重复／倒退')
        if slot.valid and (slot.ir_raw is None or slot.axes_g is None or not np.isfinite((slot.ir_raw,*slot.axes_g)).all()):
            raise ValueError('25Hz有效载荷非法')
        reset=prev is None or slot.generation!=prev.generation or slot.valid!=prev.valid
        if reset or not slot.valid:self.refs=[CausalDcBlocker(self.config['reference_dc_alpha']) for _ in range(4)]
        refs=(0.,0.,0.,0.)
        if slot.valid:
            values=(float(np.linalg.norm(slot.axes_g)),*slot.axes_g)
            if reset:
                for dc,value in zip(self.refs,values):dc.reset(value)
            refs=tuple(dc.step(v)/self.config['reference_scale_g'] for dc,v in zip(self.refs,values))
        return SampleRequest(Identity(self.run_id,rid,slot.sequence,slot.generation),slot.valid,
                             reset or not slot.valid,slot.ir_raw if slot.valid else None,refs,slot.contact_ready)


class SeedConnection:
    def __init__(self,connection):self.connection=connection;self.seed=None;self.consumed=True
    def recv(self):
        message=self.connection.recv();rid,kind,payload=message
        if kind=='step':
            if not self.consumed:raise RuntimeError('unconsumed SAMPLE receipt')
            slot,controls,request,sample=payload
            self.seed=(request,sample);self.consumed=False
            return rid,kind,(slot,controls)
        return message
    def send(self,message):
        if message[1]=='ready':message=(message[0],message[1],dict(message[2],sample_ipc='one_roundtrip_exact_refs_v1'))
        if message[1]=='done' and not self.consumed:raise RuntimeError('SAMPLE receipt missing from step')
        return self.connection.send(message)
    def close(self):self.connection.close()
    def poll(self,timeout):return self.connection.poll(timeout)


class SeedRemote(original.Remote):
    def sample(self,request):
        connection=self.connection
        if connection.consumed or connection.seed is None:raise RuntimeError('duplicate/missing seeded SAMPLE')
        expected,result=connection.seed
        if (not same_request(request,expected) or not isinstance(result,SampleResult)
                or result.identity!=request.identity):raise RuntimeError('prepared SAMPLE/PS reference bits differ')
        connection.consumed=True;connection.seed=None
        return result


def ps_worker(connection,source,**kwargs):
    if __package__:
        from .joint_startup import replace_attribute
        from . import main_heart_chain,main_tail_compact
    else:
        from joint_startup import replace_attribute
        import main_heart_chain,main_tail_compact
    with replace_attribute(original,'Remote',SeedRemote),replace_attribute(main_heart_chain,'make_chain',main_tail_compact.make_chain):
        return original.ps_worker(SeedConnection(connection),source,**kwargs)


def exchange(bridge,kind,payload):
    if kind!='step':return bridge._original_exchange(kind,payload)
    if bridge._closed or bridge._fault or bridge.backend is None:
        raise RuntimeError('main bridge locked/closed/unbound: '+bridge._fault)
    bridge._request_id+=1;rid=bridge._request_id;deadline=time.monotonic()+1.
    try:
        if not bridge._worker.is_alive():raise RuntimeError('main PS exited')
        slot,controls=payload
        request=bridge._preparation.request(slot,rid,controls)
        bridge.backend.set_deadline(deadline)
        bridge._sample_requests+=1;sample=bridge.backend.sample(request);bridge._pl_requests+=1
        if not isinstance(sample,SampleResult) or sample.identity!=request.identity:raise RuntimeError('main physical response identity differs')
        if time.monotonic()>=deadline:raise TimeoutError('main outer step expired before PS send')
        bridge._connection.send((rid,'step',(slot,controls,request,sample)))
        response_id,phase,value=bridge._receive(deadline)
        if response_id!=rid:raise RuntimeError('main outer IPC request differs')
        if phase=='error':raise RuntimeError('main PS exception: '+value)
        if phase!='done':raise RuntimeError('compact main step requires one done response')
        r=sample.reply
        if (value.frame.sequence,value.pl_sequence,value.pl_epoch,value.pl_status,value.pl_latency_cycles,
            value.beta_int,value.backend_source)!=(slot.sequence,r.sequence,r.epoch,r.status,r.latency_cycles,r.beta_int,bridge.source):
            raise RuntimeError('main final frame differs from NLMS receipt')
        bridge._previous_slot=slot;bridge._preparation.previous=slot;bridge._completed_steps+=1
        return value
    except BaseException as exc:
        bridge._fault=str(exc) or type(exc).__name__;raise


def Bridge(source,target,*,run_id):
    bridge=OriginalBridge(source,target,run_id=run_id)
    if bridge._ready.get('sample_ipc')!='one_roundtrip_exact_refs_v1':
        bridge._fault='compact PS READY identity differs';bridge.close();raise RuntimeError(bridge._fault)
    bridge._preparation=Preparation(run_id)
    bridge._original_exchange=bridge._exchange
    bridge._exchange=MethodType(exchange,bridge)
    return bridge
