"""Frozen request validation with an effective25-only, hardware-free warmup."""
import multiprocessing as mp
import os
import sys
import time
from heart_v3a.live.process_chain import _RemoteBackend
from v3a_25hz_live.bridge import ProcessChain25


def worker(connection, source):
    request_id=0
    try:
        import math
        from heart_v2.runtime_main_chain import Observation
        from heart_v3a.runtime_backend import FixedNlmsBackend
        from peak_chain import PeakTimingChain
        from .frontend import Frontend25
        warm,front=PeakTimingChain(FixedNlmsBackend()),Frontend25()
        for i in range(700):
            warm.step(front.push(Observation(i,i/25.,125000+600*math.sin(2*math.pi*1.2*i/25.),(0.,0.,1.),True)))
        del warm,front
        remote=_RemoteBackend(connection,source)
        chain=None
        connection.send((0,'ready',dict(worker_pid=os.getpid(),warmup_raw=700,warmup_slots=700,
            worker_hardware_imported=any(k=='pynq' or k.startswith('pynq.') for k in sys.modules))))
        while True:
            request_id,kind,payload=connection.recv(); remote.request_id=request_id
            if kind=='close': return
            if kind=='reset' and chain is None:
                remote.epoch=payload; chain=PeakTimingChain(remote)
                connection.send((request_id,'done',chain.epoch))
            elif kind=='step' and chain is not None:
                slot,controls=payload
                if controls!=dict(beta_int=32212255,update_enabled=True,bypass=False):
                    raise RuntimeError('25Hz固定NLMS参数禁止切换')
                connection.send((request_id,'done',chain.step(slot)))
            else: raise RuntimeError('25Hz请求非法／禁止重新初始化')
    except EOFError: return
    except BaseException as exc:
        try: connection.send((request_id,'error',type(exc).__name__+': '+str(exc)))
        except (BrokenPipeError,EOFError,OSError): pass
    finally: connection.close()


class Bridge25(ProcessChain25):
    def __init__(self,source):
        if source not in ('python_fixed','pl_mmio'): raise ValueError('后端来源必须明确')
        self.source,self.backend=source,None
        self._request_id=self._completed_steps=self._pl_requests=0
        self._fault=''; self._closed=self._forced=self._initialized=False; self._ready={}
        ctx=mp.get_context('spawn')
        self._connection,child=ctx.Pipe()
        self._worker=ctx.Process(target=worker,args=(child,source),name='effective25-ps-only')
        started=time.monotonic()
        try:
            self._worker.start(); child.close()
            message=self._receive(time.monotonic()+60.)
            if message[:2]!=(0,'ready'): raise RuntimeError('25Hz预热失败：'+str(message))
            self._ready=message[2]
            if self._ready['worker_pid']==os.getpid() or self._ready['worker_hardware_imported']:
                raise RuntimeError('子进程硬件隔离身份不符')
        except BaseException:
            child.close(); self.close(); raise
        self._warm_seconds=time.monotonic()-started

    def info(self):
        return {**super().info(),'raw_hz':25,'processing_hz':25,
                'strategy':'effective25_process25_spawn_parent_hardware'}
