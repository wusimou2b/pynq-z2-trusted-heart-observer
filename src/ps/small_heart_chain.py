"""Private placement adapter; original history, SQI and final gate stay on PS."""
from dataclasses import replace

if __package__:
    from .small_heart_model import BRANCHES, PrepRequest, BankRequest, PrepResult, BankResult
else:
    from small_heart_model import BRANCHES, PrepRequest, BankRequest, PrepResult, BankResult


class BranchView:
    """Only the returned branch state: deliberately no step() calculation."""
    def __init__(self, result=None):
        self.reset()
        if result is not None:
            self.previous = result.filtered
            self.ibis = result.ibis
            self.sample_index = result.sample_index
            self.last_peak_index = result.last_peak_index
            self.last_peak_position = result.last_peak_position
            self.accepted_peak_count = result.accepted_peak_count

    def reset(self):
        self.previous = 0.
        self.ibis = ()
        self.sample_index = self.accepted_peak_count = 0
        self.last_peak_index = self.last_peak_position = None


def make_chain(base):
    import numpy as np
    from heart_v2.runtime_main_chain import RuntimeFrame

    class Chain(base):
        def _reset_signals(self):
            super()._reset_signals()
            self.detectors = {k: BranchView() for k in BRANCHES}

        def _process(self, slot):
            # Same logical stages as frozen Rate25Chain._process. Only the
            # placements of PPG/mean and branch detectors have changed.
            reset = (self.previous is None or slot.generation != self.previous.generation
                     or slot.valid != self.previous.valid)
            if reset or not slot.valid:
                self._reset_signals()
            frame = RuntimeFrame(slot.sequence, slot.available_time_s, slot.valid,
                '原始安全代号／有效区间变化' if reset else '', contact_ok=slot.valid,
                contact_ready=slot.contact_ready, reason_cn=slot.reason)
            identity = self.backend.identity(slot.sequence, slot.generation)
            prep = self.config['preprocess']
            refs = (0., 0., 0., 0.)
            if slot.valid:
                current = (float(np.linalg.norm(slot.axes_g)), *slot.axes_g)
                if reset:
                    for dc, value in zip(self.ref_dc, current):
                        dc.reset(value)
                refs = tuple(dc.step(v)/prep['reference_scale_g']
                             for dc, v in zip(self.ref_dc, current))
            prepared = self.backend.prep(PrepRequest(identity, slot.valid, reset or not slot.valid,
                slot.ir_raw if slot.valid else None, tuple(refs[1:])))
            if not isinstance(prepared, PrepResult) or prepared.identity != identity:
                raise RuntimeError('PREP reply identity differs')
            self._reply = reply = prepared.reply
            if reply.epoch != self.epoch:
                raise RuntimeError('后端epoch不符')
            if not slot.valid:
                return frame
            if not reply.status & 1:
                raise RuntimeError('输入量化溢出，已发invalid，禁止自动恢复')
            raw, mean = prepared.raw, prepared.mean
            candidate = reply.candidate_int/65536
            clipped = bool(reply.status & 4)
            joint = self.selector.step(raw, candidate, refs[0], refs[1:], clipped=clipped)
            frame = replace(frame, raw=raw, mean=mean, nlms_candidate=candidate,
                joint_output=joint.output, nlms_mix=joint.mix, learning_update=True,
                internal_weight_clipped=clipped, joint_reason=joint.reason,
                joint_protection=joint.protection_triggered, magnitude_reference=refs[0],
                reference_x=refs[1], reference_y=refs[2], reference_z=refs[3])
            motion = self.motion_classifier.step(np.asarray(refs[1:])*prep['reference_scale_g'])
            bank = self.backend.bank(BankRequest(identity, prepared.core_epoch,
                                                 joint.output, slot.contact_ready))
            if (not isinstance(bank, BankResult) or bank.identity != identity
                    or bank.core_epoch != prepared.core_epoch or tuple(bank.branches) != BRANCHES):
                raise RuntimeError('BANK4 reply identity or branch set differs')
            qualities, bpms = {}, {}
            for key, state in bank.branches.items():
                detector = self.detectors[key] = BranchView(state)
                qualities[key] = self.quality_components[key].step(
                    state.filtered*prep['ppg_scale_counts'], peak=state.peak,
                    ibis=detector.ibis, allowed=slot.contact_ready)
                bpms[key+'_bpm'] = (state.bpm if qualities[key].label != 'bad'
                    and len(detector.ibis) >= 2 and self._bpm_in_range(state.bpm) else None)
            frame = replace(frame, motion=motion.label, motion_ready=motion.ready,
                motion_rms_g=motion.rms_g,
                **{k+'_quality': s.label for k, s in qualities.items()},
                **{k+'_quality_reason': s.reason_cn for k, s in qualities.items()}, **bpms)
            return self._final_output(frame, qualities)

    return Chain
