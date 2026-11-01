"""Explicit 25 Hz PS chain. No hardware loading, sensor access or auto tuning."""
from collections import deque
from dataclasses import replace
import numpy as np

from heart_v2.runtime_main_chain import RuntimeFrame, choose_route
from heart_v2.preprocess import CausalDcBlocker
from heart_v3a.axi_contract import BETA_DEFAULT
from heart_v3a.runtime_pl_chain import RuntimePlMainChain, PlRuntimeFrame
from heart_v3a.live.statistics_fast import CachedSosHeartRateDetector
from .frontend import Slot
from .policy import configuration, PROCESS_HZ, MEAN_WINDOW, peak_fresh
from .state import BranchQuality25, Motion25, QualityCache25
from .benefit import Selector25


class Rate25Chain:
    def __init__(self,backend):
        if backend.source not in ('python_fixed','pl_mmio'):
            raise ValueError('后端来源必须明确')
        self.backend = backend
        self.config = configuration()
        self.epoch = backend.reset()
        self._controls = (BETA_DEFAULT,True,False)
        self._reply = None
        self.fault = ''
        self.previous = None
        self._reset_signals()

    def _reset_signals(self):
        prep = self.config['preprocess']
        self.ppg_dc = CausalDcBlocker(prep['ppg_dc_alpha'])
        self.ref_dc = [CausalDcBlocker(prep['reference_dc_alpha']) for _ in range(4)]
        self.mean_window = deque(maxlen=MEAN_WINDOW)
        self.selector = Selector25()
        self.motion_classifier = Motion25()
        if not hasattr(self,'detectors'):
            self.detectors = {k:CachedSosHeartRateDetector(PROCESS_HZ,**self.config['heartrate'])
                              for k in ('raw','mean','nlms','joint')}
            self.output_detector = CachedSosHeartRateDetector(PROCESS_HZ,**self.config['heartrate'])
        else:
            for d in self.detectors.values(): d.reset()
            self.output_detector.reset()
        cache = QualityCache25()
        self.quality_components = {k:BranchQuality25(cache) for k in self.detectors}
        self.previous_route = 'none'

    def step(self,slot):
        if self.fault:
            raise RuntimeError('25Hz主链故障锁定：'+self.fault)
        try:
            if not isinstance(slot,Slot):
                raise ValueError('必须为有原始来源的25Hz槽')
            expected = 0 if self.previous is None else self.previous.sequence+1
            if slot.sequence != expected:
                raise ValueError('25Hz槽重复／缺失／倒退')
            if self.previous is not None and slot.available_time_s <= self.previous.available_time_s:
                raise ValueError('25Hz可用时刻重复／倒退')
            if slot.valid and (slot.ir_raw is None or slot.axes_g is None
                    or not np.isfinite((slot.ir_raw,*slot.axes_g)).all()):
                raise ValueError('25Hz有效载荷非法')
            self._reply = None
            frame = self._process(slot)
            r = self._reply
            self.previous = slot
            return PlRuntimeFrame(frame,self.backend.source,BETA_DEFAULT,r.sequence,r.epoch,
                                  r.status,r.latency_cycles,False)
        except Exception as exc:
            self.fault = str(exc)
            self._reset_signals()
            raise

    def _send(self,slot,raw,refs,valid,reset):
        reply = RuntimePlMainChain._send_packet(self,slot,raw,refs,valid,valid,reset)
        if reply.epoch != self.epoch:
            raise RuntimeError('后端epoch不符')
        return reply

    def _bpm_in_range(self,bpm):
        p = self.config['heartrate']
        return bpm is not None and np.isfinite(bpm) and p['min_bpm'] <= bpm <= p['max_bpm']

    def _process(self,slot):
        reset = (self.previous is None or slot.generation != self.previous.generation
                 or slot.valid != self.previous.valid)
        if reset or not slot.valid:
            self._reset_signals()
        frame = RuntimeFrame(slot.sequence,slot.available_time_s,slot.valid,
                             '原始安全代号／有效区间变化' if reset else '',
                             contact_ok=slot.valid,contact_ready=slot.contact_ready,
                             reason_cn=slot.reason)
        if not slot.valid:
            self._send(slot,0.,(0.,0.,0.),False,True)
            return frame
        prep = self.config['preprocess']
        current = (float(np.linalg.norm(slot.axes_g)),*slot.axes_g)
        if reset:
            self.ppg_dc.reset(slot.ir_raw)
            for dc,v in zip(self.ref_dc,current): dc.reset(v)
        raw = self.ppg_dc.step(slot.ir_raw)/prep['ppg_scale_counts']
        refs = [dc.step(v)/prep['reference_scale_g'] for dc,v in zip(self.ref_dc,current)]
        reply = self._send(slot,raw,tuple(refs[1:]),True,reset)
        if not reply.status & 1:
            # Explicit invalid packet was consumed; do not continue a corrupt stream.
            raise RuntimeError('输入量化溢出，已发invalid，禁止自动恢复')
        candidate = reply.candidate_int/65536
        clipped = bool(reply.status & 4)
        joint = self.selector.step(raw,candidate,refs[0],refs[1:],clipped=clipped)
        self.mean_window.append(raw)
        frame = replace(frame,raw=raw,mean=float(np.mean(self.mean_window)),
                        nlms_candidate=candidate,joint_output=joint.output,nlms_mix=joint.mix,
                        learning_update=True,internal_weight_clipped=clipped,
                        joint_reason=joint.reason,joint_protection=joint.protection_triggered,
                        magnitude_reference=refs[0],reference_x=refs[1],reference_y=refs[2],reference_z=refs[3])
        motion = self.motion_classifier.step(np.asarray(refs[1:])*prep['reference_scale_g'])
        qualities = {}
        bpms = {}
        for key,value in dict(raw=frame.raw,mean=frame.mean,nlms=candidate,joint=joint.output).items():
            detector = self.detectors[key]
            state = detector.step(value,slot.contact_ready)
            qualities[key] = self.quality_components[key].step(
                state.filtered*prep['ppg_scale_counts'],peak=state.peak,ibis=detector.ibis,
                allowed=slot.contact_ready)
            bpms[key+'_bpm'] = (state.bpm if qualities[key].label != 'bad'
                               and len(detector.ibis)>=2 and self._bpm_in_range(state.bpm) else None)
        frame = replace(frame,motion=motion.label,motion_ready=motion.ready,motion_rms_g=motion.rms_g,
                        **{k+'_quality':s.label for k,s in qualities.items()},
                        **{k+'_quality_reason':s.reason_cn for k,s in qualities.items()},**bpms)
        return self._final_output(frame,qualities)

    def _final_output(self,frame,qualities):
        route = (choose_route(frame.motion,{k:s.label for k,s in qualities.items()},frame.nlms_mix)
                 if frame.contact_ready and frame.motion_ready else 'none')
        changed = route != self.previous_route
        if changed or route == 'none': self.output_detector.reset()
        self.previous_route = route
        if route == 'none':
            return replace(frame,route_changed=changed,reason_cn='等待接触／运动／质量历史')
        side = 'joint' if route == 'nlms' else route
        value = frame.joint_output if route == 'nlms' else getattr(frame,route)
        state = self.output_detector.step(value,True)
        peak = self.output_detector.last_peak_index
        age = None if peak is None else self.output_detector.sample_index-1-peak
        count = len(self.output_detector.ibis)
        allowed = count>=2 and peak_fresh(age) and self._bpm_in_range(state.bpm)
        return replace(frame,selected_route=route,selected_signal=value,selected_quality=qualities[side].label,
                       route_changed=changed,output_ibi_count=count,output_peak_age_samples=age,
                       output_filtered_counts=state.filtered*self.config['preprocess']['ppg_scale_counts'],
                       bpm=state.bpm if allowed else None,output_allowed=bool(allowed),
                       reason_cn='25Hz心率估计' if allowed else '等待选路后有效峰／心率范围或峰龄阻断')
