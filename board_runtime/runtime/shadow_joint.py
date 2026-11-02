"""Owner-local shadow observation and borrowed spatial video resources."""
import math
import time
from functools import partial

import numpy as np

if __package__:
    from .yuyv_joint_binding import SharedYuyvResources
    from .spatial_camera import CameraResources
    from .yuyv_reference import validate_yuyv
    from .roi_motion_core import integer
    from . import yuyv_joint_binding as base_binding
    from .yuyv_joint_binding import HeartHardware
    from .heart_video_binding import SnapshotVideoBinding, PynqHeartOwner
    from .spatial_owner import SpatialOwner, verify_pair
    from .shadow_video_core import profile
    from .joint_startup import replace_attribute
else:
    from yuyv_joint_binding import SharedYuyvResources
    from spatial_camera import CameraResources
    from yuyv_reference import validate_yuyv
    from roi_motion_core import integer
    import yuyv_joint_binding as base_binding
    from yuyv_joint_binding import HeartHardware
    from heart_video_binding import SnapshotVideoBinding, PynqHeartOwner
    from spatial_owner import SpatialOwner, verify_pair
    from shadow_video_core import profile
    from joint_startup import replace_attribute


def protocol(elapsed_ns):
    integer(elapsed_ns, 'elapsed_ns')
    index = elapsed_ns//15_000_000_000 if elapsed_ns < 60_000_000_000 else None
    return dict(phase_index=index, instructed_label=('STATIC','LIGHT','HEAVY','STATIC')[index] if index is not None else 'STATIC',
        remaining_seconds=math.ceil(((index+1)*15_000_000_000-elapsed_ns)/1e9) if index is not None else None,
        segment_part=('transition' if elapsed_ns%15_000_000_000 < 2_000_000_000 else 'stable')
            if index is not None else 'post_protocol',
        manual_stop_available=True, labels_are_ground_truth=False)


class TappedMailbox:
    """Delegate exactly once; observe the already-built snapshot in this owner."""
    def __init__(self, original, fusion, *, clock_ns=time.monotonic_ns):
        self.original, self.fusion, self.clock_ns = original, fusion, clock_ns

    def publish(self, snapshot):
        result = self.original.publish(snapshot)
        self.fusion.observe(snapshot.latest, observed_ns=self.clock_ns())
        return result

    def __getattr__(self, name):
        return getattr(self.original, name)


class SharedSpatialResources(SharedYuyvResources, CameraResources):
    """Reuse original shared-owner close plus camera-qualified spatial open/reference."""
    def __init__(self, *args, fusion, **kwargs):
        self.shadow = fusion
        super().__init__(*args, **kwargs)

    def process_ready_frame(self, raw, *, sequence, timestamp_ns):
        if self.formal_epoch is None:
            raise RuntimeError('shadow video not armed')
        self._available()
        validate_yuyv(raw, camera_geometry=True)
        self.captured += 1
        self._stage('new_display_frame')
        self.pending = self.hdmi.newframe()
        self._stage('pl_color_roi_writeback')
        result = self.port.process(raw, self.pending, sequence=sequence, timestamp_ns=timestamp_ns)
        if self.port.take_completed_frame() is not self.pending:
            raise RuntimeError('destination ownership changed')
        if len(self.retained) < 2:
            self.retained.append((raw.copy(), np.array(self.pending, copy=True), dict(result)))
        self._stage('hdmi_submit')
        with self.guard.budget(1, 'frame submit'):
            while not int(self.guard.read(4)) & 0x1000:
                self._available()
                time.sleep(.001)
            self._available()
            checked_ns = self.motion_clock()
            shadow = self.shadow.consume(result, now_ns=checked_ns)
            action = protocol(timestamp_ns-self.formal_epoch)
            cv = self.api.cv2
            cv.rectangle(self.pending, (160,120), (479,359), (0,255,0,0), 1)
            for x in (240,320,400):cv.line(self.pending, (x,120), (x,359), (0,120,0,0), 1)
            for y in (200,280):cv.line(self.pending, (160,y), (479,y), (0,120,0,0), 1)
            prompt = ('DO:'+action['instructed_label']+' '+str(action['remaining_seconds'])+'s'
                      if action['phase_index'] is not None else 'DO:STATIC | stop manually when ready')
            lines = [prompt, 'SHADOW ONLY | seq='+str(sequence),
                     'IMU:'+shadow['imu']['label']+' VIDEO:'+shadow['video']['label'],
                     'FUSION:'+shadow['label']+' '+shadow['evidence_mode']]
            for index, text in enumerate(lines):
                cv.putText(self.pending, text, (10,20+index*20), cv.FONT_HERSHEY_SIMPLEX, .43, (0,255,255,0), 1)
            self.hdmi.writeframe(self.pending)
        self.pending = None
        self.submitted += 1
        self._stage('ready')
        return dict(source_sequence=sequence, read_completed_ns=timestamp_ns, vision=result,
                    shadow=shadow, protocol=action, hdmi_submitted=True)


class HeartSpatialOwner(SpatialOwner):
    """New spatial identity; exactly the original PYNQ IIC/NLMS/FIFO ports."""
    heart_ports = PynqHeartOwner.heart_ports

    def __init__(self, directory, hardware_factory=HeartHardware, lease=None, **kwargs):
        super().__init__(directory, hardware_factory, lease, **kwargs)


def spatial_prepare_pair(directory):
    # The old preparation routine needs hashes under its two formal argument keys.
    # No file or manifest is renamed/replaced; HeartSpatialOwner loads the actual new filenames.
    pair = verify_pair(directory)
    return dict(pair_integrity_verified=True, files={
        'heart_v3b25_yuyv.bit': pair['files']['heart_v3b25_spatial.bit'],
        'heart_v3b25_yuyv.hwh': pair['files']['heart_v3b25_spatial.hwh']})


class ShadowBinding(SnapshotVideoBinding):
    def __init__(self, *args, fusion, **kwargs):
        self.fusion = fusion
        kwargs.setdefault('owner_factory', HeartSpatialOwner)
        super().__init__(*args, **kwargs)

    def prepare(self, *args, **kwargs):
        with replace_attribute(base_binding, 'verify_pair', spatial_prepare_pair), \
             replace_attribute(base_binding, 'SharedYuyvResources', partial(SharedSpatialResources, fusion=self.fusion)):
            session = super().prepare(*args, **kwargs)
        original_arm = self.video_runner.arm
        def arm(epoch):
            self.video.arm(epoch)
            return original_arm(epoch)
        self.video_runner.arm = arm
        session._preflight.update(shadow_fusion=True, shadow_heart_control_enabled=False,
            shadow_rule_sha256=profile()['sha256'], spatial_pair_loaded=True)
        return session

    def report(self):
        return dict(super().report(), shadow_fusion=self.fusion.report(), shadow_rule_sha256=profile()['sha256'],
                    shadow_heart_control_enabled=False, spatial_pair_loaded=True)
