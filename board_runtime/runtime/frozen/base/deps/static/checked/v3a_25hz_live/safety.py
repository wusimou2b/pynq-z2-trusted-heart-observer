"""Acquisition-rate veto only; no FIR, PL, peak detector or file I/O here."""
from dataclasses import dataclass, replace
import threading

import numpy as np
from heart_v2.contact import ContactGate
from heart_v2.runtime_main_chain import _validated_observation, runtime_config


@dataclass(frozen=True)
class SafetyState:
    generation: int
    contact_ready: bool
    raw_observed: int
    latest_read_ns: int | None
    fault: str


class RawSafety:
    """Mirror RawFrontend's raw-only permission rules, checked in differential tests.

    One acquisition writer; readers hold this short lock, never the PS/PL lock.
    The durable frontend remains the only producer of processable Slots.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._gate = ContactGate(**runtime_config()['contact'])
        self._previous = None
        self._generation = self._count = 0
        self._ready = False
        self._read_ns = None
        self._fault = ''

    def observe(self, observation, read_ns):
        with self._lock:
            if self._fault:
                raise RuntimeError('原始安全故障锁定：' + self._fault)
            try:
                ob = _validated_observation(observation)
                previous = self._previous
                if previous and (ob.sequence <= previous.sequence or ob.time_s <= previous.time_s):
                    raise ValueError('时间或序号重复／倒退')
                if type(read_ns) is not int or read_ns < 0 or self._read_ns is not None and read_ns < self._read_ns:
                    raise ValueError('原始读取完成时刻非法')
            except Exception as exc:
                self._fault = str(exc)
                self._ready = False
                self._generation += 1
                self._gate.reset()
                raise
            tolerance = 4*np.spacing(max(ob.time_s, .04))
            bad = bool(previous and (ob.sequence != previous.sequence+1 or ob.time_s-previous.time_s > .04+tolerance))
            bad |= bool(ob.reset or not ob.pair_ok or not ob.accel_valid or not ob.pl_fifo_ok
                        or ob.error.strip() or ob.contact_ok is False)
            if bad:
                self._gate.reset()
                contact = None
            else:
                contact = self._gate.step(ob.ir_raw, ob.contact_ok)
                bad = not contact.derived_contact_ok or self._ready and not contact.trusted_allowed
            if bad:
                self._generation += 1
                self._ready = False
            else:
                self._ready = bool(contact.trusted_allowed)
            self._previous, self._read_ns = ob, read_ns
            self._count += 1

    def snapshot(self):
        with self._lock:
            return SafetyState(self._generation, self._ready, self._count, self._read_ns, self._fault)

    def guard(self, slot, frame, read_ns, *, now_ns, max_age_ns=1_000_000_000):
        if type(max_age_ns) is not int or not 0 < max_age_ns <= 1_000_000_000:
            raise ValueError('工程显示年龄必须为正且不放宽旧1秒保护')
        state = self.snapshot()
        allowed = (not state.fault and state.contact_ready and slot.valid and slot.contact_ready
                   and slot.generation == state.generation and frame.sequence == slot.sequence
                   and 0 <= now_ns-read_ns <= max_age_ns and frame.output_allowed)
        if allowed:
            return frame
        return replace(frame, bpm=None, output_allowed=False,
                       reason_cn='原始安全许可／结果新鲜度阻断')
