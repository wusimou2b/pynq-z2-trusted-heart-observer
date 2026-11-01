"""Six-confirmation binding restricted to the newly spawned, hardware-free PS process."""
import gc
from pathlib import Path
import sys

from entry25_guard import validate, activate, identity

ROOT = Path(__file__).resolve().parent


class ReadyIdentity:
    """Only enrich the existing readiness response; forward all per-sample IPC intact."""
    def __init__(self, connection, metadata):
        self.connection, self.metadata = connection, metadata

    def send(self, message):
        if message[:2] == (0, 'ready'):
            message = (0, 'ready', dict(message[2], **self.metadata))
        return self.connection.send(message)

    def recv(self):
        return self.connection.recv()

    def poll(self, timeout):
        return self.connection.poll(timeout)

    def close(self):
        return self.connection.close()


def worker(connection, source):
    original = module = None
    try:
        validate(ROOT)
        activate(ROOT)
        from effective25.bridge import worker as frozen_worker
        import peak_chain as module
        from entry25_candidate import DelayedPeakChain
        if any(name == 'pynq' or name.startswith('pynq.') for name in sys.modules):
            raise RuntimeError('候选计算子进程不得导入硬件')
        original = module.PeakTimingChain
        module.PeakTimingChain = DelayedPeakChain
        metadata = dict(identity(ROOT), ps_gc_enabled_at_ready=gc.isenabled())
        frozen_worker(ReadyIdentity(connection, metadata), source)
    except BaseException as exc:
        try:
            connection.send((0, 'error', type(exc).__name__+': '+str(exc)))
        except (BrokenPipeError, EOFError, OSError):
            pass
    finally:
        if original is not None:
            module.PeakTimingChain = original
        connection.close()
