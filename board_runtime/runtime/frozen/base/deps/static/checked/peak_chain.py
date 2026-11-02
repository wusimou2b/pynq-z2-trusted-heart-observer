"""25 Hz v2: fractional peak timing and warm selected-branch waveform only."""
from dataclasses import replace

from heart_v2.runtime_main_chain import choose_route
from v3a_rate25.chain import Rate25Chain
from v3a_rate25.policy import PROCESS_HZ, peak_fresh
from peak_timing import FractionalPeakDetector


class PeakTimingChain(Rate25Chain):
    def _reset_signals(self):
        super()._reset_signals()
        # The base resets the entire signal/quality/selector state unchanged.
        # Replace just the detector family on initial construction, then reuse
        # coefficients on later resets. No mutation of old classes or globals.
        if not isinstance(self.output_detector,FractionalPeakDetector):
            self.detectors = {k:FractionalPeakDetector(PROCESS_HZ,**self.config['heartrate'])
                              for k in self.detectors}
            self.output_detector = FractionalPeakDetector(PROCESS_HZ,**self.config['heartrate'])

    def _final_output(self,frame,qualities):
        route = (choose_route(frame.motion,{k:s.label for k,s in qualities.items()},frame.nlms_mix)
                 if frame.contact_ready and frame.motion_ready else 'none')
        changed = route != self.previous_route
        if changed or route == 'none':
            self.output_detector.reset()
        self.previous_route = route
        if route == 'none':
            return replace(frame,route_changed=changed,reason_cn='等待接触／运动／质量历史')
        side = 'joint' if route == 'nlms' else route
        value = frame.joint_output if route == 'nlms' else getattr(frame,route)
        # previous is this tick's filtered value after the branch step, not its
        # previous tick. Only the waveform crosses; no peaks/IBIs/BPM are copied.
        filtered = self.detectors[side].previous
        state = self.output_detector.step_filtered(filtered,True)
        peak = self.output_detector.last_peak_index
        age = None if peak is None else self.output_detector.sample_index-1-peak
        count = len(self.output_detector.ibis)
        allowed = count>=2 and peak_fresh(age) and self._bpm_in_range(state.bpm)
        return replace(frame,selected_route=route,selected_signal=value,selected_quality=qualities[side].label,
                       route_changed=changed,output_ibi_count=count,output_peak_age_samples=age,
                       output_filtered_counts=state.filtered*self.config['preprocess']['ppg_scale_counts'],
                       bpm=state.bpm if allowed else None,output_allowed=bool(allowed),
                       reason_cn='25Hz精细峰时刻心率估计' if allowed else '等待选路后有效峰／心率范围或峰龄阻断')
