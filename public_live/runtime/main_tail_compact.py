"""Allocation-only PS tail candidate; original arithmetic and final gate retained."""
if __package__:
    from .main_heart_chain import make_chain as original_chain
    from .main_heart_mmio import SampleRequest, SampleResult
    from .small_heart_model import BRANCHES
else:
    from main_heart_chain import make_chain as original_chain
    from main_heart_mmio import SampleRequest, SampleResult
    from small_heart_model import BRANCHES


def make_chain(base):
    import numpy as np
    from heart_v2.runtime_main_chain import RuntimeFrame

    class CompactChain(original_chain(base)):
        def _process(self, slot):
            reset = (self.previous is None or slot.generation != self.previous.generation
                     or slot.valid != self.previous.valid)
            if reset or not slot.valid:
                self._reset_signals()
            fields = dict(sequence=slot.sequence, time_s=slot.available_time_s, valid=slot.valid,
                          reset_reason='原始安全代号／有效区间变化' if reset else '',
                          contact_ok=slot.valid, contact_ready=slot.contact_ready, reason_cn=slot.reason)
            identity = self.backend.identity(slot.sequence, slot.generation)
            prep = self.config['preprocess']; refs = (0., 0., 0., 0.)
            if slot.valid:
                current = (float(np.linalg.norm(slot.axes_g)), *slot.axes_g)
                if reset:
                    for dc, value in zip(self.ref_dc, current): dc.reset(value)
                refs = tuple(dc.step(v)/prep['reference_scale_g'] for dc, v in zip(self.ref_dc, current))
            sample = self.backend.sample(SampleRequest(identity, slot.valid, reset or not slot.valid,
                slot.ir_raw if slot.valid else None, refs, slot.contact_ready))
            if (not isinstance(sample, SampleResult) or sample.identity != identity
                or sample.reply.sequence != slot.sequence or sample.reply.epoch != self.epoch or sample.core_epoch <= 0):
                raise RuntimeError('continuous sample reply identity/epoch differs')
            self._reply = reply = sample.reply
            if not slot.valid: return RuntimeFrame(**fields)
            if not reply.status & 1 or reply.status & 8 or tuple(sample.branches) != BRANCHES:
                raise RuntimeError('continuous original valid/status/branches differ; no fallback')
            fields.update(raw=sample.raw, mean=sample.mean, nlms_candidate=reply.candidate_int/65536,
                joint_output=sample.joint, nlms_mix=sample.mix, learning_update=True,
                internal_weight_clipped=bool(reply.status & 4), joint_reason=sample.reason,
                joint_protection=sample.protection, magnitude_reference=refs[0],
                reference_x=refs[1], reference_y=refs[2], reference_z=refs[3])
            motion = self.motion_classifier.step(np.asarray(refs[1:])*prep['reference_scale_g'])
            fields.update(motion=motion.label, motion_ready=motion.ready, motion_rms_g=motion.rms_g)
            qualities = {}
            for key, state in sample.branches.items():
                # Private views are not published. Reuse their storage; receipts remain immutable.
                detector = self.detectors[key]
                detector.previous = state.filtered; detector.ibis = state.ibis
                detector.sample_index = state.sample_index; detector.last_peak_index = state.last_peak_index
                detector.last_peak_position = state.last_peak_position
                detector.accepted_peak_count = state.accepted_peak_count
                quality = qualities[key] = self.quality_components[key].step(
                    state.filtered*prep['ppg_scale_counts'], peak=state.peak,
                    ibis=detector.ibis, allowed=slot.contact_ready)
                fields[key+'_quality'] = quality.label
                fields[key+'_quality_reason'] = quality.reason_cn
                fields[key+'_bpm'] = (state.bpm if quality.label != 'bad' and len(detector.ibis) >= 2
                                     and self._bpm_in_range(state.bpm) else None)
            return self._final_output(RuntimeFrame(**fields), qualities)
    return CompactChain
