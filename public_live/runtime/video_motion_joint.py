"""Complete motion binding at the original continuous owner's video boundary."""
import time

if __package__:
    from . import shadow_joint
    from .shadow_joint import SharedSpatialResources, ShadowBinding, HeartSpatialOwner, protocol
    from .joint_startup import replace_attribute
else:
    import shadow_joint
    from shadow_joint import SharedSpatialResources, ShadowBinding, HeartSpatialOwner, protocol
    from joint_startup import replace_attribute

PREPARATION_FRAMES = 4
MotionHeartOwner = HeartSpatialOwner


class MotionResources(SharedSpatialResources):
    """Warm normal HDMI frame stores before heart capture; retain original close."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.preparation_submissions = 0

    def open(self):
        identity = super().open()
        # Normal writeframe transfers ownership. No private-cache manipulation,
        # direct freeing, spatial-core call or formal counter increment here.
        for _ in range(PREPARATION_FRAMES):
            self._available()
            self.pending = self.hdmi.newframe()
            self.pending[...] = 0
            self.api.cv2.putText(self.pending, 'PREPARING | heart capture not started',
                (10, 24), self.api.cv2.FONT_HERSHEY_SIMPLEX, .43, (0, 255, 255, 0), 1)
            with self.guard.budget(1, 'preparation HDMI submit'):
                while not int(self.guard.read(4)) & 0x1000:
                    self._available()
                    time.sleep(.001)
                self._available()
                self.hdmi.writeframe(self.pending)
            self.pending = None
            self.preparation_submissions += 1
        return dict(identity, preparation_hdmi_submissions=self.preparation_submissions,
            preparation_touches_spatial_history=False, formal_counts_include_preparation=False)


class MotionBinding(ShadowBinding):
    def prepare(self, *args, **kwargs):
        with replace_attribute(shadow_joint, 'SharedSpatialResources', MotionResources):
            session = super().prepare(*args, **kwargs)
        session._preflight.update(preparation_hdmi_submissions_requested=PREPARATION_FRAMES,
            original_start_order_retained=True, per_register_timing_enabled=False)
        return session

    def report(self):
        return dict(super().report(), original_start_order_retained=True,
            preparation_hdmi_submissions=getattr(self.video, 'preparation_submissions', 0),
            per_register_timing_enabled=False)
