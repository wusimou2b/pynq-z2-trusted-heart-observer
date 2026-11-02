"""Reuse qualified current-branch PL intervals, never a cached published BPM.

Only the final output policy changes: intervals may precede route selection,
but must follow the most recent unqualified sample on that same branch.
No new detectors, hardware requests, IPC messages or unbounded histories.
"""
from dataclasses import replace
from statistics import median

TAG = 'qualified_current_branch_intervals_v1'
BRANCHES = ('raw', 'mean', 'nlms', 'joint')


def wrap_factory(factory):
    def make(base):
        from heart_v2.runtime_main_chain import choose_route
        from v3a_rate25.policy import peak_fresh
        original = factory(base)

        class Chain(original):
            def _reset_signals(self):
                super()._reset_signals()
                self._qualified_peak_floor = dict.fromkeys(BRANCHES, 0)

            def _final_output(self, frame, qualities):
                ready = frame.valid and frame.contact_ready and frame.motion_ready
                # A bad-quality/contact interval cannot donate historical IBIs.
                # Counter is the validated current SAMPLE's branch counter.
                for key in BRANCHES:
                    if not ready or qualities[key].label == 'bad':
                        self._qualified_peak_floor[key] = self.detectors[key].accepted_peak_count
                route = (choose_route(frame.motion, {k:s.label for k,s in qualities.items()}, frame.nlms_mix)
                         if ready else 'none')
                changed = route != self.previous_route
                self.previous_route = route
                if route == 'none':
                    return replace(frame,route_changed=changed,reason_cn='等待接触／运动／质量历史')
                side = 'joint' if route == 'nlms' else route
                detector = self.detectors[side]
                # Three eligible peaks give two wholly eligible intervals.
                count = min(len(detector.ibis), max(0,detector.accepted_peak_count-self._qualified_peak_floor[side]-1))
                peak = detector.last_peak_index
                age = None if peak is None else detector.sample_index-1-peak
                bpm = getattr(frame,side+'_bpm')
                # Startup/quality recovery may leave older unqualified IBIs in
                # the PL ring. Only its qualified suffix may contribute. Once
                # the full ring is qualified the existing PL BPM is reused.
                if count >= 2 and count < len(detector.ibis):
                    bpm = 1500./median(detector.ibis[-count:])
                allowed = count >= 2 and peak_fresh(age) and self._bpm_in_range(bpm)
                value = frame.joint_output if route == 'nlms' else getattr(frame,route)
                return replace(frame,selected_route=route,selected_signal=value,selected_quality=qualities[side].label,
                    route_changed=changed,output_ibi_count=count,output_peak_age_samples=age,
                    output_filtered_counts=detector.previous*self.config['preprocess']['ppg_scale_counts'],
                    bpm=bpm if allowed else None,output_allowed=bool(allowed),
                    reason_cn='25Hz精细峰时刻心率估计' if allowed else '等待选路后有效峰／心率范围或峰龄阻断')
        return Chain
    return make
