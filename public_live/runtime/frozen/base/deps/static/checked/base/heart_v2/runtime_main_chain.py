"""V2 逐样本主链；旧算法和板端文件保持不变。"""
from dataclasses import asdict, dataclass, replace
from copy import deepcopy
from collections import deque
from numbers import Integral, Real
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from .contact import ContactGate
from .preprocess import CausalDcBlocker
from .nlms import Nlms4
from .joint_benefit import JointBenefitSelector
from .heartrate import CausalHeartRateDetector
from .runtime_state import MotionClassifier, BranchQuality


ALGORITHM = dict(beta=.03, epsilon=.001, weight_limit=8., rho=.5,
                 channels=3, taps_per_axis=4, delay_samples=0)


@dataclass(frozen=True)
class Observation:
    sequence: int
    time_s: float
    ir_raw: float
    axes_g: tuple[float, float, float]
    pair_ok: bool
    contact_ok: bool | None = None
    reset: bool = False
    pl_fifo_ok: bool = True
    accel_valid: bool = True
    error: str = ''


@dataclass(frozen=True)
class RuntimeFrame:
    sequence: int
    time_s: float
    valid: bool
    reset_reason: str
    learning_update: bool = False
    raw: float | None = None
    mean: float | None = None
    nlms_candidate: float | None = None
    joint_output: float | None = None
    nlms_mix: float = 0.
    motion: str | None = None
    motion_ready: bool = False
    contact_ok: bool = False
    contact_ready: bool = False
    raw_quality: str = 'bad'
    mean_quality: str = 'bad'
    nlms_quality: str = 'bad'
    joint_quality: str = 'bad'
    selected_route: str = 'none'
    selected_signal: float | None = None
    bpm: float | None = None
    output_allowed: bool = False
    reason_cn: str = ''
    magnitude_reference: float | None = None
    reference_x: float | None = None
    reference_y: float | None = None
    reference_z: float | None = None
    internal_weight_clipped: bool = False
    joint_reason: str = ''
    joint_protection: bool = False
    motion_rms_g: float | None = None
    raw_quality_reason: str = ''
    mean_quality_reason: str = ''
    nlms_quality_reason: str = ''
    joint_quality_reason: str = ''
    selected_quality: str = 'bad'
    output_ibi_count: int = 0
    output_peak_age_samples: int | None = None
    output_filtered_counts: float | None = None
    route_changed: bool = False
    raw_bpm: float | None = None
    mean_bpm: float | None = None
    nlms_bpm: float | None = None
    joint_bpm: float | None = None


def parse_boolean(value, name, *, optional=False):
    """只接受明确布尔表示，避免字符串 False 被当成 True。"""
    if optional and (value is None or value is pd.NA or
                     isinstance(value, Real) and np.isnan(value)):
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, Real) and np.isfinite(value) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ('true', '1', '1.0'):
            return True
        if normalized in ('false', '0', '0.0'):
            return False
    raise ValueError(f'{name} 必须是明确的 True／False 或 0／1')


def _finite_number(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f'{name} 必须为有限数')
    return float(value)


def runtime_config(config=None):
    """只读取旧配置中的采集、预处理、接触和共同判峰项。"""
    if config is None:
        path = Path(__file__).parents[1] / 'config/arena_v2_primed.yaml'
        config = yaml.safe_load(path.read_text(encoding='utf-8'))
    try:
        result = deepcopy({key: config[key] for key in
            ('sample_rate_hz', 'preprocess', 'contact', 'heartrate')})
        if _finite_number(result['sample_rate_hz'], '采样率') != 50.:
            raise ValueError('新主链只支持标称 50 Hz')
        prep = result['preprocess']
        for key in ('ppg_dc_alpha', 'reference_dc_alpha'):
            if not 0 <= _finite_number(prep[key], key) < 1:
                raise ValueError('去直流系数必须在 [0,1)')
        for key in ('ppg_scale_counts', 'reference_scale_g'):
            if _finite_number(prep[key], key) <= 0:
                raise ValueError('缩放系数必须为正')
        contact = result['contact']
        for key in ('low_ir_threshold', 'baseline_jump_fraction', 'minimum_pulse_amplitude'):
            if _finite_number(contact[key], key) <= 0:
                raise ValueError('接触阈值必须为正')
        if not 0 <= _finite_number(contact['baseline_alpha'], 'baseline_alpha') < 1:
            raise ValueError('接触基线系数必须在 [0,1)')
        heart = result['heartrate']
        for values, key, minimum in [(contact, 'amplitude_window_samples', 2),
            (contact, 'recovery_samples', 1), (heart, 'ibi_history', 2)]:
            value = values[key]
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < minimum:
                raise ValueError(f'{key} 必须为至少 {minimum} 的整数')
        if not 0 < _finite_number(heart['min_bpm'], 'min_bpm') < _finite_number(heart['max_bpm'], 'max_bpm'):
            raise ValueError('心率范围非法')
        if not 0 < _finite_number(heart['threshold_alpha'], 'threshold_alpha') <= 1:
            raise ValueError('判峰阈值系数非法')
        if _finite_number(heart['threshold_scale'], 'threshold_scale') <= 0:
            raise ValueError('判峰阈值比例非法')
    except (KeyError, TypeError) as exc:
        raise ValueError('配置缺少主链必需项') from exc
    return result


def _validated_observation(observation):
    if not isinstance(observation, Observation):
        raise ValueError('输入必须为 Observation')
    seq = observation.sequence
    if isinstance(seq, (bool, np.bool_)) or not isinstance(seq, Integral) or seq < 0:
        raise ValueError('序号必须为非负整数')
    time = _finite_number(observation.time_s, '时间')
    if time < 0:
        raise ValueError('时间必须非负')
    ir = _finite_number(observation.ir_raw, 'IR')
    flags = {key: parse_boolean(getattr(observation, key), key) for key in
             ('pair_ok', 'reset', 'pl_fifo_ok', 'accel_valid')}
    recorded = parse_boolean(observation.contact_ok, 'contact_ok', optional=True)
    try:
        axes = np.asarray(observation.axes_g, dtype=float)
    except (ValueError, TypeError) as exc:
        raise ValueError('加速度必须为三轴数值') from exc
    if axes.shape != (3,) or np.isinf(axes).any() or flags['pair_ok'] and not np.isfinite(axes).all():
        raise ValueError('配对加速度必须为三轴有限数；仅未配对行可缺失')
    if not isinstance(observation.error, str):
        raise ValueError('错误字段必须为文本')
    return replace(observation, sequence=int(seq), time_s=time, ir_raw=ir,
                   axes_g=tuple(axes), contact_ok=recorded, **flags)


def choose_route(motion, qualities, mix):
    """只决定候选次序；采集／接触硬阻断由调用者优先处理。"""
    if motion not in ('static', 'light', 'heavy'):
        return 'none'
    if motion == 'static':
        order = ('mean', 'raw')
    elif mix > 0 and qualities['joint'] != 'bad':
        return 'nlms'
    else:
        order = ('raw', 'mean')
    return next((side for side in order if qualities[side] != 'bad'), 'none')


class RuntimeMainChain:
    def __init__(self, config=None):
        self.config = runtime_config(config)
        self.gate = ContactGate(**self.config['contact'])
        self.previous = None
        self.previous_valid = False
        self._reset_signals()

    def _reset_signals(self):
        prep = self.config['preprocess']
        self.ppg_dc = CausalDcBlocker(prep['ppg_dc_alpha'])
        self.ref_dc = [CausalDcBlocker(prep['reference_dc_alpha']) for _ in range(4)]
        self.mean_window = deque(maxlen=4)
        self.nlms = Nlms4(beta=ALGORITHM['beta'], channels=3, protected=False,
                         weight_limit=ALGORITHM['weight_limit'], epsilon=ALGORITHM['epsilon'])
        self.selector = JointBenefitSelector()
        self.motion_classifier = MotionClassifier()
        self.detectors = {key: CausalHeartRateDetector(50., **self.config['heartrate'])
                          for key in ('raw', 'mean', 'nlms', 'joint')}
        self.quality_components = {key: BranchQuality() for key in self.detectors}
        self.output_detector = CausalHeartRateDetector(50., **self.config['heartrate'])
        self.previous_route = 'none'

    def _clock_reasons(self, observation):
        if self.previous is None:
            return ['首次样本']
        if observation.sequence <= self.previous.sequence or observation.time_s <= self.previous.time_s:
            raise ValueError('时间或序号重复／倒退')
        reasons = []
        if observation.sequence != self.previous.sequence + 1:
            reasons.append('序号缺口')
        # 仅吸收时间相减的浮点表示误差，不放宽 40 ms 缺口门槛。
        tolerance = 4*np.spacing(max(observation.time_s, self.previous.time_s, .04))
        if observation.time_s-self.previous.time_s > .04+tolerance:
            reasons.append('时间缺口')
        return reasons

    def step(self, observation):
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
        learning = self.nlms.step(raw, references[1:], update=learning_update)
        candidate = raw-float(np.clip(learning.estimate,
            -ALGORITHM['rho']*abs(raw), ALGORITHM['rho']*abs(raw)))
        joint = self.selector.step(raw, candidate, references[0], references[1:],
            valid=valid, contact_allowed=learning_update, reset=bool(reasons), clipped=learning.clipped)
        self.mean_window.append(raw)
        frame = replace(frame, raw=raw, mean=float(np.mean(self.mean_window)),
            nlms_candidate=candidate, joint_output=joint.output, nlms_mix=joint.mix,
            learning_update=learning_update, internal_weight_clipped=learning.clipped,
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


def replay_main_chain(source, config=None):
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
    chain = RuntimeMainChain(config)
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
        records.append(asdict(chain.step(observation)))
    result = pd.DataFrame(records)
    # 固定可空数值列的类型，未来出现首个有效 BPM 不改变历史行表示。
    for key in ('raw', 'mean', 'nlms_candidate', 'joint_output', 'selected_signal', 'bpm',
                'magnitude_reference', 'reference_x', 'reference_y', 'reference_z',
                'motion_rms_g', 'output_peak_age_samples', 'output_filtered_counts'):
        result[key] = pd.to_numeric(result[key], errors='raise').astype(float)
    for key in ('raw_bpm', 'mean_bpm', 'nlms_bpm', 'joint_bpm'):
        result[key] = pd.to_numeric(result[key], errors='raise').astype(float)
    return result
