"""IIC-only extension to the verified shared YUYV/heart lifecycle."""
if __package__:
    from .yuyv_joint_binding import YuyvHeartOwner, YuyvJointBinding, HeartHardware
    from .iic_handoff import HandoffTransport, sensor_bus_type
    from .joint_startup import replace_attribute
else:
    from yuyv_joint_binding import YuyvHeartOwner, YuyvJointBinding, HeartHardware
    from iic_handoff import HandoffTransport, sensor_bus_type
    from joint_startup import replace_attribute


class HandoffOwner(YuyvHeartOwner):
    def __init__(self, directory, hardware_factory=HeartHardware, lease=None, *, library=None, **kwargs):
        if library is None:
            if __package__: from .iic_handoff_build import load_verified
            else: from iic_handoff_build import load_verified
            library = load_verified(directory)
        super().__init__(directory, hardware_factory, lease, library=library, **kwargs)

    def heart_ports(self):
        # Scope the existing owner's construction only; physical ownership,
        # close/quarantine and three DMA release order remain its exact methods.
        if __package__: from . import yuyv_joint_binding as original
        else: import yuyv_joint_binding as original
        with replace_attribute(original, 'NativeIicTransport', HandoffTransport):
            return super().heart_ports()


class HandoffBinding(YuyvJointBinding):
    def __init__(self, *args, owner_factory=HandoffOwner, **kwargs):
        super().__init__(*args, owner_factory=owner_factory, **kwargs)

    def prepare(self, base, output, *, hardware=False):
        import heart_axi_live
        with replace_attribute(heart_axi_live, 'SensorBus', sensor_bus_type(heart_axi_live.SensorBus)):
            session = super().prepare(base, output, hardware=hardware)
        session._preflight.update(iic_implementation_unchanged=False,
            iic_complete_read=True, iic_state_snapshot_fields=21,
            pairing_policy_unchanged=True, iic_transaction_timeout_seconds=.050)
        return session
