"""复用冻结V2的PS规则，候选只能来自明确标记的后端；无摄像头扩展。"""
from collections import deque
from dataclasses import asdict,dataclass,replace
from numbers import Real
import numpy as np
import pandas as pd
from heart_v2.runtime_main_chain import (Observation,RuntimeFrame,RuntimeMainChain,
    runtime_config,_validated_observation,choose_route)
from heart_v2.contact import ContactGate
from heart_v2.preprocess import CausalDcBlocker
from heart_v2.joint_benefit import JointBenefitSelector
from heart_v2.runtime_state import MotionClassifier,BranchQuality
from heart_v2.heartrate import CausalHeartRateDetector
from .axi_contract import NlmsPacket,validate_packet,BETA_DEFAULT
from .fixed_math import quantize
from .runtime_backend import FixedNlmsBackend

@dataclass(frozen=True)
class PlRuntimeFrame:
    frame:RuntimeFrame
    backend_source:str
    beta_int:int
    pl_sequence:int|None
    pl_epoch:int|None
    pl_status:int|None
    pl_latency_cycles:int|None
    control_changed:bool

class RuntimePlMainChain(RuntimeMainChain):
    def __init__(self,backend,config=None):
        if backend.source not in ('python_fixed','pl_mmio'): raise ValueError('后端来源必须明确')
        self.backend=backend; self._fault='';self._controls=(BETA_DEFAULT,True,False)
        self._last_controls=None; self.control_events=[];self._reply=None
        super().__init__(config)

    def reset(self):
        epoch=self.backend.reset()
        self._fault='';self.previous=None;self.previous_valid=False;self.gate.reset()
        self._last_controls=None;self._reply=None;self._reset_signals()
        return epoch

    def step(self,observation,*,beta_int=BETA_DEFAULT,update_enabled=True,bypass=False):
        observation=_validated_observation(observation)
        validate_packet(NlmsPacket(observation.sequence,0,(0,0,0),0,beta_int))
        if type(update_enabled) is not bool or type(bypass) is not bool: raise ValueError('运行时控制必须为bool')
        controls=(beta_int,update_enabled,bypass)
        changed=self._last_controls is not None and controls!=self._last_controls
        if changed:
            self.control_events.append(dict(sequence=observation.sequence,
                old_beta_int=self._last_controls[0],new_beta_int=beta_int,
                old_controls=self._last_controls,new_controls=controls,
                flags=(int(update_enabled)<<1)|(int(bypass)<<3)))
            self.selector=JointBenefitSelector();self.output_detector.reset();self.previous_route='none'
        self._last_controls=self._controls=controls;self._reply=None
        if self._fault:
            frame=RuntimeFrame(observation.sequence,observation.time_s,False,'PL故障锁定',
                reason_cn='须显式reset恢复：'+self._fault)
        else:
            try: frame=self._process_observation(observation)
            except Exception as exc:
                self._fault=str(exc);self._reset_signals();self.gate.reset();self.previous_valid=False
                frame=RuntimeFrame(observation.sequence,observation.time_s,False,'PL／处理故障',reason_cn=self._fault)
        r=self._reply
        return PlRuntimeFrame(frame,self.backend.source,beta_int,r.sequence if r else None,
            r.epoch if r else None,r.status if r else None,r.latency_cycles if r else None,changed)

    def _send_packet(self,observation,raw,references,valid,learning_update,reset_learning):
        words=[quantize(v,24,16) for v in (raw,*references)] if valid else []
        payload_ok=valid and not any(w.saturated for w in words)
        flags=int(payload_ok)|(int(learning_update and payload_ok)<<1)|(int(reset_learning)<<2)|(int(self._controls[2])<<3)
        packet=NlmsPacket(observation.sequence,words[0].value if payload_ok else 0,
            tuple(w.value for w in words[1:]) if payload_ok else (0,0,0),flags,self._controls[0])
        reply=self.backend.transact(packet)
        if reply.sequence!=packet.sequence or reply.beta_int!=packet.beta_int or reply.status&~15 or reply.status&8:
            raise RuntimeError('后端错序／实际β／状态或算术故障')
        if bool(reply.status&1)!=payload_ok: raise RuntimeError('后端valid与完整输入包不一致')
        self._reply=reply
        return reply

    def _reset_signals(self):
        prep = self.config['preprocess']
        self.ppg_dc = CausalDcBlocker(prep['ppg_dc_alpha'])
        self.ref_dc = [CausalDcBlocker(prep['reference_dc_alpha']) for _ in range(4)]
        self.mean_window = deque(maxlen=4)
        self.selector = JointBenefitSelector()
        self.motion_classifier = MotionClassifier()
        self.detectors = {key: CausalHeartRateDetector(50., **self.config['heartrate'])
                          for key in ('raw', 'mean', 'nlms', 'joint')}
        self.quality_components = {key: BranchQuality() for key in self.detectors}
        self.output_detector = CausalHeartRateDetector(50., **self.config['heartrate'])
        self.previous_route = 'none'

    def _process_observation(self, observation):
        observation = _validated_observation(observation)
        reasons = self._clock_reasons(observation)
        if observation.reset:
            reasons.append('显式重置')
        if reasons:
            self.gate.reset()
        faults = []
        if not observation.pair_ok:
            faults.append('PPG／加速度未配对')
        if not observation.pl_fifo_ok:
            faults.append('PL FIFO 故障')
        if not observation.accel_valid:
            faults.append('加速度无效')
        if observation.error.strip():
            faults.append('采集错误：'+observation.error)
        if faults:
            self.gate.reset()
            valid = contact_ok = contact_ready = False
            contact = None
        else:
            contact = self.gate.step(observation.ir_raw, observation.contact_ok)
            contact_ok = bool(contact.derived_contact_ok and observation.contact_ok is not False)
            valid = contact_ok
            contact_ready = bool(valid and contact.trusted_allowed)
            if observation.contact_ok is False:
                faults.append('记录接触阻断')
                self.gate.reset()
            elif not contact.derived_contact_ok:
                faults.append({'low_ir': 'IR 过低／手指离开',
                    'baseline_jump': 'IR 基线突变／接触压力异常'}.get(contact.reason, '接触异常'))
        if valid != self.previous_valid:
            reasons.append('连续有效区间开始' if valid else '连续有效区间结束')
        if reasons or not valid:
            self._reset_signals()
        self.previous = observation
        self.previous_valid = valid
        frame = RuntimeFrame(observation.sequence, observation.time_s, valid,
            '；'.join(reasons), contact_ok=contact_ok, contact_ready=contact_ready,
            reason_cn='；'.join(faults) if faults else '等待接触恢复' if not contact_ready else '等待主链接通')
        if not valid:
            self._send_packet(observation, 0., (0.,0.,0.), False, False, bool(reasons))
            return frame
        prep = self.config['preprocess']
        current = np.r_[np.linalg.norm(observation.axes_g), observation.axes_g]
        if reasons:
            self.ppg_dc.reset(observation.ir_raw)
            for dc, value in zip(self.ref_dc, current):
                dc.reset(value)
        raw = (self.ppg_dc.step(observation.ir_raw) if prep['ppg_dc_alpha'] else observation.ir_raw) / prep['ppg_scale_counts']
        references = [(dc.step(value) if prep['reference_dc_alpha'] else value) / prep['reference_scale_g']
                      for dc, value in zip(self.ref_dc, current)]
        learning_update = bool(valid and contact.update_allowed)
        learning_update = learning_update and self._controls[1]
        reply = self._send_packet(observation, raw, tuple(references[1:]), True, learning_update, bool(reasons))
        if not reply.status & 1:
            self.gate.reset(); self._reset_signals(); self.previous_valid=False
            return replace(frame, valid=False, contact_ok=False, contact_ready=False,
                reset_reason=frame.reset_reason+'；输入量化溢出', reason_cn='输入量化溢出，已送invalid并清PL学习状态')
        candidate = reply.candidate_int / 65536
        clipped = bool(reply.status & 4)
        joint = self.selector.step(raw, candidate, references[0], references[1:],
            valid=valid, contact_allowed=learning_update, reset=bool(reasons), clipped=clipped)
        self.mean_window.append(raw)
        frame = replace(frame, raw=raw, mean=float(np.mean(self.mean_window)),
            nlms_candidate=candidate, joint_output=joint.output, nlms_mix=joint.mix,
            learning_update=learning_update, internal_weight_clipped=clipped,
            joint_reason=joint.reason, joint_protection=joint.protection_triggered,
            magnitude_reference=references[0], reference_x=references[1],
            reference_y=references[2], reference_z=references[3])
        # 状态使用 g 单位去直流三轴，不把归一化后的参考误当加速度。
        motion = self.motion_classifier.step(np.asarray(references[1:])*prep['reference_scale_g'])
        quality_states = {}
        branch_bpms = {}
        for key, value in dict(raw=frame.raw, mean=frame.mean,
                              nlms=frame.nlms_candidate, joint=frame.joint_output).items():
            detector = self.detectors[key]
            state = detector.step(value, frame.contact_ready)
            quality_states[key] = self.quality_components[key].step(
                state.filtered*prep['ppg_scale_counts'], peak=state.peak,
                ibis=detector.ibis, allowed=frame.contact_ready)
            branch_bpms[key+'_bpm'] = (state.bpm if quality_states[key].label != 'bad'
                and len(detector.ibis) >= 2 else None)
        frame = replace(frame, motion=motion.label, motion_ready=motion.ready,
            motion_rms_g=motion.rms_g,
            **{key+'_quality': state.label for key, state in quality_states.items()},
            **{key+'_quality_reason': state.reason_cn for key, state in quality_states.items()}, **branch_bpms)
        return self._final_output(frame, quality_states)

    def _final_output(self, frame, qualities):
        if not frame.contact_ready:
            route, reason = 'none', '等待接触恢复'
        elif not frame.motion_ready:
            route, reason = 'none', '等待运动状态历史'
        else:
            route = choose_route(frame.motion, {key: state.label for key, state in qualities.items()}, frame.nlms_mix)
            if self._controls[2]: route = 'raw' if qualities['raw'].label != 'bad' else 'none'
            reason = '信号质量不足：'+qualities['raw'].reason_cn if route == 'none' else ''
        changed = route != self.previous_route
        # 切路重建独立判峰状态；正常 mix 小步变化不清空历史。
        if changed or route == 'none':
            self.output_detector.reset()
        self.previous_route = route
        if route == 'none':
            return replace(frame, reason_cn=reason, route_changed=changed)
        side = 'joint' if route == 'nlms' else route
        value = frame.joint_output if route == 'nlms' else getattr(frame, route)
        state = self.output_detector.step(value, True)
        last_peak = self.output_detector.last_peak_index
        age = None if last_peak is None else self.output_detector.sample_index-1-last_peak
        count = len(self.output_detector.ibis)
        allowed = bool(count >= 2 and age is not None and age <= 75 and
                       state.bpm is not None and np.isfinite(state.bpm))
        if not allowed:
            reason = '有效峰值过期' if age is not None and age > 75 else '等待选路后的两个新峰间隔'
        elif qualities[side].label == 'medium':
            reason = '质量中：输出心率估计'
        else:
            reason = '质量优：输出心率估计'
        return replace(frame, selected_route=route, selected_signal=value,
            selected_quality=qualities[side].label, route_changed=changed,
            output_ibi_count=count, output_peak_age_samples=age,
            output_filtered_counts=state.filtered*self.config['preprocess']['ppg_scale_counts'],
            bpm=state.bpm if allowed else None, output_allowed=allowed, reason_cn=reason)

def replay_pl_chain(source, config=None, backend=None):
    """只消费原始观测；phase 和已有质量／心率字段不进入计算。"""
    required = ('sequence', 'ir_raw', 'ax_g', 'ay_g', 'az_g')
    if not isinstance(source, pd.DataFrame) or not len(source) or any(key not in source for key in required):
        raise ValueError('输入缺少原始观测列或为空')
    if 'time_s' in source:
        times = source['time_s'].to_numpy()
    elif 'timestamp_us' in source:
        stamps = source['timestamp_us'].to_numpy(dtype=float)
        times = (stamps-stamps[0])/1e6
    else:
        raise ValueError('输入缺少 time_s／timestamp_us')
    chain = RuntimePlMainChain(backend or FixedNlmsBackend(), config)
    records = []
    for i, values in enumerate(source.to_dict('records')):
        seq = values['sequence']
        # 旧加载器统一返回 float 数组；只把有限整数值转换，不吞非法值。
        if isinstance(seq, Real) and not isinstance(seq, (bool, np.bool_)) and np.isfinite(seq) and seq == np.floor(seq):
            seq = int(seq)
        pair = values.get('pair_ok', bool(np.isfinite([values[k] for k in ('ax_g','ay_g','az_g')]).all()))
        error = values.get('error', '')
        if error is None or isinstance(error, Real) and np.isnan(error):
            error = ''
        observation = Observation(seq, times[i], values['ir_raw'],
            tuple(values[k] for k in ('ax_g','ay_g','az_g')), pair,
            contact_ok=values.get('contact_ok'), reset=values.get('reset', False),
            pl_fifo_ok=values.get('pl_fifo_ok', True), accel_valid=values.get('accel_valid', True), error=error)
        result = chain.step(observation)
        records.append({**asdict(result.frame), **{k:v for k,v in asdict(result).items() if k != 'frame'}})
    result = pd.DataFrame(records)
    # 固定可空数值列的类型，未来出现首个有效 BPM 不改变历史行表示。
    for key in ('raw', 'mean', 'nlms_candidate', 'joint_output', 'selected_signal', 'bpm',
                'magnitude_reference', 'reference_x', 'reference_y', 'reference_z',
                'motion_rms_g', 'output_peak_age_samples', 'output_filtered_counts'):
        result[key] = pd.to_numeric(result[key], errors='raise').astype(float)
    for key in ('raw_bpm', 'mean_bpm', 'nlms_bpm', 'joint_bpm'):
        result[key] = pd.to_numeric(result[key], errors='raise').astype(float)
    return result


