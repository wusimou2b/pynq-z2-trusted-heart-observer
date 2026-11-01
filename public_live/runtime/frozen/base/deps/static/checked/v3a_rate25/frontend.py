"""Raw-rate supervision and causal anti-aliasing, independent of slow PS work."""
from collections import deque
from dataclasses import dataclass, replace
import math

import numpy as np
from scipy.signal import firwin

from heart_v2.contact import ContactGate
from heart_v2.runtime_main_chain import _validated_observation, runtime_config

ANTIALIAS = tuple(float(v) for v in firwin(21,8.75,fs=50,window=('kaiser',5.)))
FILTER_DELAY_SECONDS = .2


@dataclass(frozen=True)
class Slot:
    sequence: int
    source_sequences: tuple[int,int]
    source_times: tuple[float,float]
    available_time_s: float
    signal_time_s: float | None
    support_sequences: tuple[int,int] | None
    support_times: tuple[float,float] | None
    generation: int
    valid: bool
    contact_ready: bool
    ir_raw: float | None
    axes_g: tuple[float,float,float] | None
    reason: str


class RawFrontend:
    """One instance per acquisition. Faults require a new, explicit session.

    Call only after raw durability in a live adapter. This offline component
    itself makes no claim to having written raw data or having accessed IIC.
    """
    def __init__(self):
        self.gate = ContactGate(**runtime_config()['contact'])
        self.history = deque(maxlen=len(ANTIALIAS))
        self.previous = None
        self.pending = []
        self.generation = 0
        self.contact_ready = False
        self.fault = ''
        self.raw_received = self.slots_emitted = self.valid_slots = 0

    def _invalidate(self):
        self.history.clear()
        self.contact_ready = False
        self.generation += 1

    def push(self, observation):
        if self.fault:
            raise RuntimeError('原始监督故障锁定：'+self.fault)
        try:
            ob = _validated_observation(observation)
            previous = self.previous
            if previous and (ob.sequence <= previous.sequence or ob.time_s <= previous.time_s):
                raise ValueError('时间或序号重复／倒退')
        except Exception as exc:
            self.fault = str(exc)
            self._invalidate()
            self.gate.reset()
            raise
        reasons = []
        tolerance = 4*np.spacing(max(ob.time_s, .04))
        if previous and (ob.sequence != previous.sequence+1 or ob.time_s-previous.time_s > .04+tolerance):
            reasons.append('原始序号／时间缺口')
        if ob.reset:
            reasons.append('显式重置')
        if not ob.pair_ok or not ob.accel_valid:
            reasons.append('PPG／加速度未配对或无效')
        if not ob.pl_fifo_ok or ob.error.strip():
            reasons.append('采集／FIFO错误：'+ob.error)
        if ob.contact_ok is False:
            reasons.append('记录接触阻断')
        if reasons:
            self.gate.reset()
            contact = None
        else:
            contact = self.gate.step(ob.ir_raw, ob.contact_ok)
            if not contact.derived_contact_ok:
                reasons.append('原始接触异常：'+contact.reason)
            elif self.contact_ready and not contact.trusted_allowed:
                reasons.append('原始脉搏幅度恢复许可撤销')
        raw_good = not reasons
        if not raw_good:
            self._invalidate()
        else:
            self.history.append(ob)
            self.contact_ready = bool(contact.trusted_allowed)
        self.previous = ob
        self.raw_received += 1
        self.pending.append((ob,raw_good,self.contact_ready,self.generation,'；'.join(reasons)))
        if len(self.pending) < 2:
            return None
        pair = self.pending
        self.pending = []
        valid = (all(v[1] for v in pair) and pair[0][3] == pair[1][3]
                 and len(self.history) == len(ANTIALIAS))
        ready = valid and all(v[2] for v in pair)
        if valid:
            h = list(self.history)
            values = np.array([(v.ir_raw,*v.axes_g) for v in h])
            filtered = np.asarray(ANTIALIAS) @ values[::-1]
            ir, axes = float(filtered[0]), tuple(float(x) for x in filtered[1:])
            signal_time = h[10].time_s
            support_seq = (h[0].sequence,h[-1].sequence)
            support_times = (h[0].time_s,h[-1].time_s)
            reason = '' if ready else '等待原始接触恢复'
        else:
            ir = axes = signal_time = support_seq = support_times = None
            reason = '；'.join(v[4] for v in pair if v[4]) or '等待连续21点抗混叠历史'
        slot = Slot(self.slots_emitted,tuple(v[0].sequence for v in pair),
                    tuple(v[0].time_s for v in pair),ob.time_s,signal_time,
                    support_seq,support_times,self.generation,bool(valid),bool(ready),ir,axes,reason)
        self.slots_emitted += 1
        self.valid_slots += int(valid)
        return slot

    def guard(self, slot, frame, *, now_s, max_age_s):
        if (not math.isfinite(now_s) or not math.isfinite(max_age_s) or max_age_s <= 0
                or now_s < slot.available_time_s):
            raise ValueError('输出新鲜度时刻／期限非法')
        allowed = (not self.fault and self.contact_ready and slot.valid and slot.contact_ready
                   and slot.generation == self.generation
                   and now_s-slot.available_time_s <= max_age_s
                   and frame.sequence == slot.sequence and frame.output_allowed)
        if allowed:
            return frame
        return replace(frame,bpm=None,output_allowed=False,reason_cn='原始安全许可／结果新鲜度阻断')

    def audit(self):
        pending = len(self.pending)
        consumed = 2*self.slots_emitted
        return dict(raw_received=self.raw_received,slots_emitted=self.slots_emitted,
                    valid_slots=self.valid_slots,invalid_slots=self.slots_emitted-self.valid_slots,
                    pending_raw=pending,pending_sequence=self.pending[0][0].sequence if pending else None,
                    consumed_raw=consumed,count_identity=self.raw_received == consumed+pending)
