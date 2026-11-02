"""25 Hz PS-only spawn worker; frozen parent bridge checks every full reply."""
import multiprocessing as mp
import os
import sys
import time

from heart_v3a.live.process_chain import ProcessChain, _RemoteBackend


def _worker25(connection, source):
    request_id = 0
    try:
        import math
        from heart_v2.runtime_main_chain import Observation
        from heart_v3a.runtime_backend import FixedNlmsBackend
        from v3a_rate25.frontend import RawFrontend
        from peak_chain import PeakTimingChain
        warm, front = PeakTimingChain(FixedNlmsBackend()), RawFrontend()
        for i in range(1400):
            slot = front.push(Observation(i, i/50., 125000+600*math.sin(2*math.pi*1.2*i/50.),
                                          (0., 0., 1.), True))
            if slot is not None:
                warm.step(slot)
        del warm, front
        remote = _RemoteBackend(connection, source)
        chain = None
        connection.send((0, 'ready', dict(worker_pid=os.getpid(), warmup_raw=1400, warmup_slots=700,
            worker_hardware_imported=any(k == 'pynq' or k.startswith('pynq.') for k in sys.modules))))
        while True:
            request_id, kind, payload = connection.recv()
            remote.request_id = request_id
            if kind == 'close':
                return
            if kind == 'reset' and chain is None:
                remote.epoch = payload
                chain = PeakTimingChain(remote)
                connection.send((request_id, 'done', chain.epoch))
            elif kind == 'step' and chain is not None:
                slot, controls = payload
                if controls != dict(beta_int=32212255, update_enabled=True, bypass=False):
                    raise RuntimeError('25Hz固定NLMS参数禁止切换')
                connection.send((request_id, 'done', chain.step(slot)))
            else:
                raise RuntimeError('25Hz请求非法／禁止重新初始化')
    except EOFError:
        return
    except BaseException as exc:
        try:
            connection.send((request_id, 'error', type(exc).__name__+': '+str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


class ProcessChain25(ProcessChain):
    """Reuse frozen full-message validation/closing, not the 50 Hz worker."""
    def __init__(self, source):
        if source not in ('python_fixed', 'pl_mmio'):
            raise ValueError('后端来源必须明确')
        self.source, self.backend = source, None
        self._request_id = self._completed_steps = self._pl_requests = 0
        self._fault = ''
        self._closed = self._forced = self._initialized = False
        self._ready = {}
        context = mp.get_context('spawn')
        self._connection, child = context.Pipe()
        self._worker = context.Process(target=_worker25, args=(child, source), name='v3a-25hz-ps-only')
        started = time.monotonic()
        try:
            self._worker.start()
            child.close()
            message = self._receive(time.monotonic()+60.)
            if message[:2] != (0, 'ready'):
                raise RuntimeError('25Hz子进程预热失败：'+str(message))
            self._ready = message[2]
            if self._ready['worker_pid'] == os.getpid() or self._ready['worker_hardware_imported']:
                raise RuntimeError('子进程硬件隔离身份不符')
        except BaseException:
            child.close()
            self.close()
            raise
        self._warm_seconds = time.monotonic()-started

    def reset(self):
        if self._initialized:
            raise RuntimeError('25Hz会话只允许初始化一次，不能reset恢复')
        epoch = super().reset()
        self._initialized = True
        return epoch

    def step(self, slot):
        if not self._initialized:
            raise RuntimeError('25Hz会话未初始化')
        return super().step(slot)

    def info(self):
        return {**super().info(), 'processing_hz': 25, 'raw_hz': 50,
                'strategy': 'raw50_process25_spawn_parent_hardware'}
