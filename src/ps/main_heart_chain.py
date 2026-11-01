"""One sample RPC, followed only by the frozen PS quality/final-output tail.

There is no PREP/history/BANK call and no fallback to their software stages.
Only IMU reference preparation, motion/SQI/routing and independent output
confirmation remain software responsibilities.
"""
from dataclasses import replace

if __package__:
    from .main_heart_mmio import SampleRequest,SampleResult
    from .small_heart_chain import BranchView
    from .small_heart_model import BRANCHES
else:
    from main_heart_mmio import SampleRequest,SampleResult
    from small_heart_chain import BranchView
    from small_heart_model import BRANCHES


def make_chain(base):
    import numpy as np
    from heart_v2.runtime_main_chain import RuntimeFrame

    class Chain(base):
        def _reset_signals(self):
            super()._reset_signals()
            self.detectors={k:BranchView() for k in BRANCHES}
            # Make an accidental call into a migrated PS stage fail visibly.
            self.ppg_dc=None;self.selector=None;self.mean_window=()

        def _process(self,slot):
            reset=(self.previous is None or slot.generation!=self.previous.generation or slot.valid!=self.previous.valid)
            if reset or not slot.valid:self._reset_signals()
            frame=RuntimeFrame(slot.sequence,slot.available_time_s,slot.valid,
                '原始安全代号／有效区间变化' if reset else '',contact_ok=slot.valid,
                contact_ready=slot.contact_ready,reason_cn=slot.reason)
            identity=self.backend.identity(slot.sequence,slot.generation)
            prep=self.config['preprocess'];refs=(0.,0.,0.,0.)
            if slot.valid:
                current=(float(np.linalg.norm(slot.axes_g)),*slot.axes_g)
                if reset:
                    for dc,value in zip(self.ref_dc,current):dc.reset(value)
                refs=tuple(dc.step(v)/prep['reference_scale_g'] for dc,v in zip(self.ref_dc,current))
            sample=self.backend.sample(SampleRequest(identity,slot.valid,reset or not slot.valid,
                slot.ir_raw if slot.valid else None,refs,slot.contact_ready))
            if (not isinstance(sample,SampleResult) or sample.identity!=identity or
                sample.reply.sequence!=slot.sequence or sample.reply.epoch!=self.epoch or sample.core_epoch<=0):
                raise RuntimeError('continuous sample reply identity/epoch differs')
            self._reply=reply=sample.reply
            if not slot.valid:return frame
            if not reply.status&1 or reply.status&8 or tuple(sample.branches)!=BRANCHES:
                raise RuntimeError('continuous original valid/status/branches differ; no fallback')
            frame=replace(frame,raw=sample.raw,mean=sample.mean,nlms_candidate=reply.candidate_int/65536,
                joint_output=sample.joint,nlms_mix=sample.mix,learning_update=True,
                internal_weight_clipped=bool(reply.status&4),joint_reason=sample.reason,
                joint_protection=sample.protection,magnitude_reference=refs[0],
                reference_x=refs[1],reference_y=refs[2],reference_z=refs[3])
            motion=self.motion_classifier.step(np.asarray(refs[1:])*prep['reference_scale_g'])
            qualities,bpms={},{}
            for key,state in sample.branches.items():
                detector=self.detectors[key]=BranchView(state)
                qualities[key]=self.quality_components[key].step(state.filtered*prep['ppg_scale_counts'],
                    peak=state.peak,ibis=detector.ibis,allowed=slot.contact_ready)
                bpms[key+'_bpm']=(state.bpm if qualities[key].label!='bad' and len(detector.ibis)>=2
                    and self._bpm_in_range(state.bpm) else None)
            frame=replace(frame,motion=motion.label,motion_ready=motion.ready,motion_rms_g=motion.rms_g,
                **{k+'_quality':s.label for k,s in qualities.items()},
                **{k+'_quality_reason':s.reason_cn for k,s in qualities.items()},**bpms)
            return self._final_output(frame,qualities)

    return Chain
