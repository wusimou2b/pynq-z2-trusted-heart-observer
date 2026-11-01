"""Experimental evidence combination. Outputs are never heart control inputs."""
from collections import Counter
if __package__:
    from .shadow_video_core import VideoCandidate
    from .shadow_imu import ImuBuffer
else:
    from shadow_video_core import VideoCandidate
    from shadow_imu import ImuBuffer

LABELS = ('STATIC', 'LIGHT', 'HEAVY', 'UNKNOWN')


def fuse(*, video, imu, pair_available, unmatched=False):
    if video not in LABELS or imu not in LABELS or type(pair_available) is not bool or type(unmatched) is not bool:
        raise ValueError('invalid shadow fusion contract')
    if unmatched and video != 'UNKNOWN' or video != 'UNKNOWN' and imu != 'UNKNOWN' and not pair_available:
        label, mode = 'UNKNOWN', 'UNMATCHED'
    elif video != 'UNKNOWN' and imu != 'UNKNOWN':
        label, mode = (video, 'AGREED') if video == imu else ('UNKNOWN', 'CONFLICT')
    elif imu != 'UNKNOWN':
        label, mode = imu, 'SINGLE_IMU'
    elif video != 'UNKNOWN':
        label, mode = video, 'SINGLE_VIDEO'
    else:
        label, mode = 'UNKNOWN', 'UNAVAILABLE'
    return dict(label=label, evidence_mode=mode, heart_control_enabled=False)


class ShadowFusion:
    def __init__(self):
        self.video = VideoCandidate()
        self.imu = ImuBuffer()
        self._imu_generation = None
        self._modes = Counter()
        self._frames = 0

    def observe(self, record, *, observed_ns):
        return self.imu.observe(record, observed_ns=observed_ns)

    def consume(self, stats, *, now_ns):
        generation = self.imu.report()['generation']
        if self._imu_generation is not None and generation != self._imu_generation:
            self.video.clear()
        self._imu_generation = generation
        video = self.video.consume(stats, now_ns=now_ns)
        if video['reason'] == 'epoch_changed':
            self.imu.invalidate_pairing()
            self._imu_generation = self.imu.report()['generation']
        imu = self.imu.match(video['timestamp_ns'], now_ns)
        if imu['generation'] != self._imu_generation:
            # An IMU reset can race the video computation; do not publish an old confirmation.
            self.video.clear()
            video.update(label='UNKNOWN', prediction_reason='imu_epoch_changed', window=[],
                         candidate=None, candidate_count=0)
            self._imu_generation = imu['generation']
        unmatched = bool(not imu['pair_available'] and imu['current_available'])
        decision = fuse(video=video['label'], imu=imu['label'], pair_available=imu['pair_available'], unmatched=unmatched)
        self._frames += 1
        self._modes[decision['evidence_mode']] += 1
        return dict(decision, video=video, imu=imu, decision_ns=now_ns, imu_generation_before=generation,
                    rule_sha256=video['rule_sha256'], schema='v3b25_shadow_fusion_v1')

    def report(self):
        return dict(frames=self._frames, modes=dict(self._modes), imu=self.imu.report(), heart_control_enabled=False,
                    independent_accuracy_verified=False)
