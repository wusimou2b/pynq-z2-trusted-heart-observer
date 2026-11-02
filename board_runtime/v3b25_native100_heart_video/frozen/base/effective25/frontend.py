"""One hardware-averaged FIFO record per slot; no second decimation/FIR."""
import math
from heart_v2.contact import ContactGate
from heart_v2.runtime_main_chain import _validated_observation
from v3a_rate25.frontend import Slot
from .policy import contact_config, MAX_GAP_SECONDS


class Supervisor25:
    """Shared policy for independent acquisition and after-flush supervisors."""
    def __init__(self):
        self.gate = ContactGate(**contact_config())
        self.previous = None
        self.generation = self.count = 0
        self.ready = False
        self.fault = ''

    def fail(self, reason):
        if not self.fault:
            self.fault = str(reason)
            self.generation += 1
        self.ready = False
        self.gate.reset()

    def advance(self, observation):
        if self.fault:
            raise RuntimeError('25Hz原始监督故障锁定：'+self.fault)
        try:
            ob = _validated_observation(observation)
            previous = self.previous
            if previous and (ob.sequence <= previous.sequence or ob.time_s <= previous.time_s):
                raise ValueError('时间或序号重复／倒退')
        except Exception as exc:
            self.fail(exc)
            raise
        reasons = []
        tolerance = 4*math.ulp(max(ob.time_s, MAX_GAP_SECONDS))
        if previous and (ob.sequence != previous.sequence+1
                         or ob.time_s-previous.time_s > MAX_GAP_SECONDS+tolerance):
            reasons.append('原始序号／时间缺口')
        if ob.reset: reasons.append('显式重置')
        if not ob.pair_ok or not ob.accel_valid: reasons.append('PPG／加速度未配对或无效')
        if not ob.pl_fifo_ok or ob.error.strip(): reasons.append('采集／FIFO错误：'+ob.error)
        if ob.contact_ok is False: reasons.append('记录接触阻断')
        if reasons:
            self.gate.reset()
            contact = None
        else:
            contact = self.gate.step(ob.ir_raw, ob.contact_ok)
            if not contact.derived_contact_ok:
                reasons.append('原始接触异常：'+contact.reason)
            elif self.ready and not contact.trusted_allowed:
                reasons.append('原始脉搏幅度恢复许可撤销')
        good = not reasons
        if not good:
            self.generation += 1
            self.ready = False
        else:
            self.ready = bool(contact.trusted_allowed)
        self.previous = ob
        self.count += 1
        return ob, good, '；'.join(reasons)


class Frontend25:
    def __init__(self):
        self.supervisor = Supervisor25()
        self.slots_emitted = self.valid_slots = 0

    def push(self, observation):
        state = self.supervisor
        ob, good, reason = state.advance(observation)
        ends, times = (ob.sequence,ob.sequence), (ob.time_s,ob.time_s)
        # These endpoints describe ONE observed FIFO record, not two ADC samples.
        slot = Slot(self.slots_emitted, ends, times, ob.time_s,
                    ob.time_s if good else None, ends if good else None, times if good else None,
                    state.generation, good, state.ready,
                    ob.ir_raw if good else None, tuple(ob.axes_g) if good else None,
                    reason if not good else '' if state.ready else '等待原始接触恢复')
        self.slots_emitted += 1
        self.valid_slots += int(good)
        return slot

    def audit(self):
        return dict(raw_received=self.supervisor.count, slots_emitted=self.slots_emitted,
                    consumed_raw=self.slots_emitted, valid_slots=self.valid_slots,
                    invalid_slots=self.slots_emitted-self.valid_slots,
                    pending_raw=0, pending_sequence=None,
                    count_identity=self.supervisor.count == self.slots_emitted)
