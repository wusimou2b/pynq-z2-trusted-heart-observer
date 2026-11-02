"""Lean spawned PS tail; exactly one owner sample phase per original step.

No physical object crosses the Pipe. Original ProcessChain supplies spawn,
60-second READY, one-second step/close, fault lock and forced-exit reporting.
"""
import gc
import math
import os
import time

if __package__:
    from .small_heart_model import Identity
    from .main_heart_mmio import SampleRequest,SampleResult
else:
    from small_heart_model import Identity
    from main_heart_mmio import SampleRequest,SampleResult


class Remote:
    def __init__(self,connection,run_id):
        self.connection,self.run_id=connection,run_id
        self.request_id=self.epoch=0;self.source='python_fixed'

    def reset(self):return self.epoch

    def identity(self,sequence,generation):
        return Identity(self.run_id,self.request_id,sequence,generation)

    def sample(self,request):
        self.connection.send((self.request_id,'sample',request))
        if not self.connection.poll(1.):raise TimeoutError('main sample owner reply missing; no retry')
        rid,kind,result=self.connection.recv()
        if (rid,kind)!=(self.request_id,'sample_reply'):raise RuntimeError('main sample IPC identity differs')
        return result


def ps_worker(connection,source,*,root,prepared_source,run_id,host_check=False):
    rid=0
    try:
        if source not in ('python_fixed','pl_mmio') or host_check and source!='python_fixed':
            raise ValueError('main sample explicit source/host boundary differs')
        if __package__:
            from .lean_ps_worker import no_hardware
            from .small_heart_worker import load_chain
            from .main_heart_chain import make_chain
        else:
            from lean_ps_worker import no_hardware
            from small_heart_worker import load_chain
            from main_heart_chain import make_chain
        with no_hardware():
            base,_,_,metadata=load_chain(root,prepared_source,host_check=host_check)
            if source=='pl_mmio' and not metadata['arm_native']:
                raise ValueError('physical main path requires original ARM Native100 preparation')
            from effective25.frontend import Frontend25
            from heart_v2.runtime_main_chain import Observation
            from heart_v3a.runtime_backend import FixedNlmsBackend
            # Identical disposable original700-point software prewarm for A/B.
            # It does not initialize, substitute for or modify physical state.
            warm=base(FixedNlmsBackend());front=Frontend25()
            for i in range(700):
                warm.step(front.push(Observation(i,i/25.,125000.+600*math.sin(2*math.pi*1.2*i/25.),(0.,0.,1.),True)))
                if getattr(warm,'_fault',''):raise RuntimeError('original warmup fault: '+warm._fault)
            del warm,front
            remote=Remote(connection,run_id);remote.source=source;chain=None
            connection.send((0,'ready',dict(metadata,worker_pid=os.getpid(),worker_hardware_imported=False,
                warmup_slots=700,warmup_raw=700,ps_gc_enabled_at_ready=gc.isenabled(),
                main_heart_mode='one_sample_continuous_v1',hardware_source=source)))
            while True:
                rid,kind,payload=connection.recv();remote.request_id=rid
                if kind=='close':return
                if kind=='reset' and chain is None:
                    remote.epoch=payload;chain=make_chain(base)(remote)
                    connection.send((rid,'done',chain.epoch))
                elif kind=='step' and chain is not None:
                    slot,controls=payload
                    if controls!=dict(beta_int=32212255,update_enabled=True,bypass=False):
                        raise ValueError('main original25 controls differ')
                    result=chain.step(slot)
                    if getattr(chain,'_fault',''):raise RuntimeError('main PS tail fault: '+chain._fault)
                    connection.send((rid,'done',result))
                else:raise RuntimeError('unknown main request or repeated reset')
    except EOFError:return
    except BaseException as exc:
        try:connection.send((rid,'error',type(exc).__name__+': '+str(exc)))
        except (OSError,EOFError):pass
    finally:connection.close()


def Bridge(source,target,*,run_id):
    from heart_v3a.live import process_chain as original
    if __package__:from .joint_startup import replace_attribute
    else:from joint_startup import replace_attribute

    class SampleBridge(original.ProcessChain):
        def __init__(self):
            self._initialized=False;self._previous_slot=None;self._sample_requests=0
            with replace_attribute(original,'_worker_main',target):super().__init__(source)
            if (self._ready.get('warmup_slots')!=700 or self._ready.get('warmup_raw')!=700
                or self._ready.get('entry_confirmation_checks')!=6
                or self._ready.get('main_heart_mode')!='one_sample_continuous_v1'
                or self._ready.get('hardware_source')!=source):
                self._fault='main ready identity differs';self.close();raise RuntimeError(self._fault)

        def reset(self):
            if self._initialized:raise RuntimeError('main bridge initializes once')
            result=super().reset();self._initialized=True;return result

        def _exchange(self,kind,payload):
            if self._closed or self._fault or self.backend is None:
                raise RuntimeError('main bridge locked/closed/unbound: '+self._fault)
            self._request_id+=1;rid=self._request_id;sample=None
            deadline=time.monotonic()+1.
            try:
                if not self._worker.is_alive():raise RuntimeError('main PS exited')
                if kind=='step':self.backend.set_deadline(deadline)
                self._connection.send((rid,kind,payload))
                while True:
                    response_id,phase,value=self._receive(deadline)
                    if response_id!=rid:raise RuntimeError('main outer IPC request differs')
                    if phase=='error':raise RuntimeError('main PS exception: '+value)
                    if phase=='sample':
                        if kind!='step' or sample is not None:raise RuntimeError('duplicate/non-step main sample phase')
                        slot,controls=payload
                        expected=Identity(run_id,rid,slot.sequence,slot.generation)
                        previous=self._previous_slot
                        reset=not slot.valid or previous is None or slot.generation!=previous.generation or slot.valid!=previous.valid
                        if (not isinstance(value,SampleRequest) or value.identity!=expected or value.valid!=slot.valid
                            or value.reset!=reset or value.beta_int!=controls['beta_int']
                            or value.ir_raw!=(slot.ir_raw if slot.valid else None) or value.contact_ready!=slot.contact_ready
                            or value.contact_allowed is not True):raise RuntimeError('main sample identity/control differs')
                        self._sample_requests+=1;sample=self.backend.sample(value);self._pl_requests+=1
                        if not isinstance(sample,SampleResult) or sample.identity!=expected:
                            raise RuntimeError('main physical response identity differs')
                        self._connection.send((rid,'sample_reply',sample))
                    elif phase=='done':
                        if kind=='step':
                            if sample is None:raise RuntimeError('main step missing sample phase')
                            r=sample.reply
                            if (value.frame.sequence,value.pl_sequence,value.pl_epoch,value.pl_status,
                                value.pl_latency_cycles,value.beta_int,value.backend_source)!=(
                                payload[0].sequence,r.sequence,r.epoch,r.status,r.latency_cycles,r.beta_int,self.source):
                                raise RuntimeError('main final frame differs from NLMS receipt')
                            self._previous_slot=payload[0];self._completed_steps+=1
                        elif value!=payload:raise RuntimeError('main reset epoch differs')
                        return value
                    else:raise RuntimeError('unknown main phase; PREP/history/BANK not allowed')
            except BaseException as exc:
                self._fault=str(exc) or type(exc).__name__;raise

        def info(self):
            return dict(super().info(),sample_requests=self._sample_requests,
                hardware_accessed=self.source=='pl_mmio',intermediate_hardware_phases=0)
    return SampleBridge()
