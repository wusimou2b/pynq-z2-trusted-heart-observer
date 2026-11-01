"""Fast acquisition veto. Keep frozen <=1 second age and generation guard."""
import threading
from v3a_25hz_live.safety import RawSafety, SafetyState
from .frontend import Supervisor25


class Safety25(RawSafety):
    def __init__(self):
        self._lock = threading.RLock()
        self._supervisor = Supervisor25()
        self._read_ns = None

    def observe(self, observation, read_ns):
        with self._lock:
            state = self._supervisor
            if state.fault:
                raise RuntimeError('25Hz原始安全故障锁定：'+state.fault)
            try:
                if (type(read_ns) is not int or read_ns < 0
                        or self._read_ns is not None and read_ns < self._read_ns):
                    raise ValueError('原始读取完成时刻非法')
                state.advance(observation)
                self._read_ns = read_ns
            except Exception as exc:
                state.fail(exc)
                raise

    def snapshot(self):
        with self._lock:
            state = self._supervisor
            return SafetyState(state.generation,state.ready,state.count,self._read_ns,state.fault)
