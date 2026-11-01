"""单拍PS进程桥。子进程没有硬件对象；所有PL调用由调用者执行。"""
import multiprocessing as mp
import os
import sys
import time


class _RemoteBackend:
    def __init__(self, connection, source):
        self.connection, self.source = connection, source
        self.request_id, self.epoch = 0, 0

    def reset(self):
        return self.epoch

    def transact(self, packet):
        self.connection.send((self.request_id, 'pl', packet))
        if not self.connection.poll(1.):
            raise TimeoutError('父进程PL回复失联，未重试')
        request_id, kind, payload = self.connection.recv()
        if (request_id, kind) != (self.request_id, 'pl_reply'):
            raise RuntimeError('PL回复IPC错序')
        return payload


def _worker_main(connection, source):
    request_id = 0
    try:
        import math
        from heart_v2.runtime_main_chain import Observation
        from heart_v3a.runtime_backend import FixedNlmsBackend
        from .processing import ReusingRuntimePlMainChain
        # 暖机只使用软件模型，完成后整个实例丢弃，不进入真实计数或学习状态。
        warm = ReusingRuntimePlMainChain(FixedNlmsBackend())
        warm.reset()
        for i in range(700):
            frame = warm.step(Observation(i, i / 50., 125000 + 600 * math.sin(2 * math.pi * 1.2 * i / 50.),
                (0., 0., 1.), True))
            if frame.pl_sequence is None or warm._fault:
                raise RuntimeError('纯软件暖机失败：' + warm._fault)
        del warm
        backend = _RemoteBackend(connection, source)
        chain = ReusingRuntimePlMainChain(backend)
        connection.send((0, 'ready', dict(worker_pid=os.getpid(),
            worker_hardware_imported=any(name == 'pynq' or name.startswith('pynq.') for name in sys.modules))))
        while True:
            request_id, kind, payload = connection.recv()
            backend.request_id = request_id
            if kind == 'close':
                return
            if kind == 'reset':
                backend.epoch = payload
                connection.send((request_id, 'done', chain.reset()))
            elif kind == 'step':
                observation, controls = payload
                result = chain.step(observation, **controls)
                if chain._fault:
                    raise RuntimeError('子进程PS故障：' + chain._fault)
                connection.send((request_id, 'done', result))
            else:
                raise RuntimeError('未知PS进程请求')
    except EOFError:
        return
    except BaseException as exc:
        try:
            connection.send((request_id, 'error', type(exc).__name__ + ': ' + str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        connection.close()


class ProcessChain:
    """调用线程唯一驱动硬件。1秒是IPC失联保护，不是50Hz验收限值。"""
    def __init__(self, source):
        if source not in ('python_fixed', 'pl_mmio'):
            raise ValueError('后端来源必须明确')
        self.source, self.backend = source, None
        self._request_id = 0
        self._fault = ''
        self._closed = False
        self._ready = {}
        self._completed_steps = self._pl_requests = 0
        self._forced = False
        context = mp.get_context('spawn')
        self._connection, child = context.Pipe()
        self._worker = context.Process(target=_worker_main, args=(child, source), name='v3a-ps-only')
        started = time.monotonic()
        try:
            self._worker.start()
            child.close()
            message = self._receive(time.monotonic() + 60.)
            if message[0:2] != (0, 'ready'):
                raise RuntimeError('子进程预热失败：' + str(message))
            self._ready = message[2]
            if self._ready['worker_pid'] == os.getpid() or self._ready['worker_hardware_imported']:
                raise RuntimeError('子进程硬件隔离身份不符')
        except BaseException:
            child.close()
            self.close()
            raise
        self._warm_seconds = time.monotonic() - started

    def attach_backend(self, backend):
        if self.backend is not None or backend.source != self.source:
            raise RuntimeError('后端已绑定或来源不符')
        self.backend = backend

    def _receive(self, deadline):
        while time.monotonic() < deadline:
            if self._connection.poll(min(.02, max(0., deadline - time.monotonic()))):
                try:
                    return self._connection.recv()
                except (EOFError, OSError) as exc:
                    raise RuntimeError('PS子进程连接关闭') from exc
            if not self._worker.is_alive():
                raise RuntimeError('PS子进程已退出：' + str(self._worker.exitcode))
        raise TimeoutError('PS子进程回复超时，未重试')

    def _exchange(self, kind, payload):
        if self._fault or self._closed:
            raise RuntimeError('PS进程故障锁定或已关闭：' + self._fault)
        if self.backend is None:
            raise RuntimeError('PS进程未绑定后端')
        self._request_id += 1
        request_id = self._request_id
        reply = None
        try:
            if not self._worker.is_alive():
                raise RuntimeError('PS子进程已退出')
            self._connection.send((request_id, kind, payload))
            deadline = time.monotonic() + 1.
            while True:
                rid, response, value = self._receive(deadline)
                if rid != request_id:
                    raise RuntimeError('PS进程IPC错序')
                if response == 'error':
                    raise RuntimeError('PS子进程异常：' + value)
                if response == 'pl':
                    from heart_v3a.axi_contract import validate_packet
                    if kind != 'step' or reply is not None:
                        raise RuntimeError('非单拍PL请求')
                    packet = validate_packet(value)
                    observation, controls = payload
                    if packet.sequence != observation.sequence or packet.beta_int != controls['beta_int']:
                        raise RuntimeError('PL请求序号／参数不符')
                    self._pl_requests += 1
                    reply = self.backend.transact(packet)
                    self._connection.send((request_id, 'pl_reply', reply))
                elif response == 'done':
                    if kind == 'step':
                        if reply is None or (value.frame.sequence, value.pl_sequence, value.pl_epoch,
                            value.pl_status, value.pl_latency_cycles, value.beta_int, value.backend_source) != (
                            payload[0].sequence, reply.sequence, reply.epoch, reply.status,
                            reply.latency_cycles, reply.beta_int, self.source):
                            raise RuntimeError('PS结果与本拍完整PL回复不符')
                        self._completed_steps += 1
                    elif value != payload:
                        raise RuntimeError('PS复位epoch不符')
                    return value
                else:
                    raise RuntimeError('未知PS进程回复')
        except BaseException as exc:
            self._fault = str(exc) or type(exc).__name__
            raise

    def reset(self):
        if self._closed or self._fault or self.backend is None:
            raise RuntimeError('PS进程未就绪／故障锁定')
        try:
            epoch = self.backend.reset()
            return self._exchange('reset', epoch)
        except BaseException as exc:
            self._fault = str(exc) or type(exc).__name__
            raise

    def step(self, observation, *, beta_int=32212255, update_enabled=True, bypass=False):
        return self._exchange('step', (observation, dict(beta_int=beta_int,
            update_enabled=update_enabled, bypass=bypass)))

    def close(self):
        if not self._closed:
            try:
                if self._worker.pid is not None and self._worker.is_alive() and not self._fault:
                    self._connection.send((self._request_id + 1, 'close', None))
            except (BrokenPipeError, EOFError, OSError):
                pass
            finally:
                self._connection.close()
                self._closed = True
        if self._worker.pid is not None:
            self._worker.join(1.)
            if self._worker.is_alive():
                self._forced = True
                self._worker.terminate()
                self._worker.join(1.)
            if self._worker.is_alive():
                raise RuntimeError('PS子进程尚未退出')

    def info(self):
        return dict(strategy='spawn_ps_parent_hardware', **self._ready,
            parent_pid=os.getpid(), warmup_seconds=getattr(self, '_warm_seconds', None),
            completed_steps=self._completed_steps, pl_requests=self._pl_requests,
            forced_termination=self._forced, exitcode=self._worker.exitcode,
            cleanup_complete=self._closed and not self._worker.is_alive(), fault=self._fault,
            timing_scope_cn='原PS处理墙钟包含IPC等待；PL调用时间仍在父进程单独计量')
