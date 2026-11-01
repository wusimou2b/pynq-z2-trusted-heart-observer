"""Recovered PYNQ-IIC heart path, single snapshot, existing shared PL video."""
if __package__:
    from .yuyv_owner import YuyvOwner
    from .yuyv_joint_binding import HeartHardware, YuyvJointBinding
    from .joint_snapshot import SnapshotAdapter
    from .heart_snapshot_worker import describe, finish_binding
else:
    from yuyv_owner import YuyvOwner
    from yuyv_joint_binding import HeartHardware, YuyvJointBinding
    from joint_snapshot import SnapshotAdapter
    from heart_snapshot_worker import describe, finish_binding


class PynqHeartOwner(YuyvOwner):
    def __init__(self, directory, hardware_factory=HeartHardware, lease=None, **kwargs):
        super().__init__(directory, hardware_factory, lease, **kwargs)

    def heart_ports(self):
        if self.state != 'bound' or not self._hardware.is_loaded():
            raise RuntimeError('heart/video owner is not bound/current')
        return dict(iic=self._hardware.heart_iic(), nlms_mmio=self._io['nlms_axi_0'],
                    fifo_mmio=self._hardware.mmio('axi_fifo_mm_s_0'))


class SnapshotVideoBinding(YuyvJointBinding):
    def __init__(self, *args, owner_factory=PynqHeartOwner, **kwargs):
        super().__init__(*args, owner_factory=owner_factory, **kwargs)
        self.adapter = SnapshotAdapter()
        self.install_error = self.restore_error = None
        self.snapshot_cleanup_confirmed = False

    def prepare(self, *args, **kwargs):
        session = super().prepare(*args, **kwargs)
        present, previous = 'snapshot' in vars(session), vars(session).get('snapshot')
        try:
            self.adapter.install(session)
            session._preflight.update(iic_runtime='original_pynq_sensorbus',
                iic_implementation_unchanged=True, iic_baseline='heart_snapshot25',
                native_iic_started=False, snapshot_probe_started=False,
                heart_snapshot_single_construction=True)
        except BaseException as exc:
            self.install_error = describe(exc)
            try:
                if present: session.snapshot = previous
                elif 'snapshot' in vars(session): del session.snapshot
                self.adapter.restored = True
            except BaseException as undo_error:
                self.restore_error = describe(undo_error)
            try: session._release_owner()
            except BaseException as release_error: self.release_error = describe(release_error)
            raise
        return session

    def report(self):
        result = super().report()
        result.update(snapshot=self.adapter.report(), install_error=self.install_error,
            restore_error=self.restore_error, snapshot_cleanup_confirmed=self.snapshot_cleanup_confirmed,
            iic_runtime='original_pynq_sensorbus', native_iic_started=False, snapshot_probe_started=False,
            iic_scope='Original heart driver; no native 50ms transaction/quiescence claim',
            construction_count_is_implementation_contract_not_measurement=True)
        return result


def finish_snapshot(binding, owner):
    result = finish_binding(binding, owner)
    binding.snapshot_cleanup_confirmed = result['cleanup_confirmed']
    return result
