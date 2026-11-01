"""Bind frozen effective25 to one joint owner; never call the old bit loader."""
from pathlib import Path

if __package__:
    from .joint_owner import JointOwner,PynqHardware,PAIR_HASHES
else:
    from joint_owner import JointOwner,PynqHardware,PAIR_HASHES


class HeartHardware(PynqHardware):
    def heart_iic(self):
        if not self.is_loaded():
            raise RuntimeError("joint Overlay changed before IIC binding")
        # Overlay._register_drivers imports pynq.lib before metadata construction.
        return self._overlay.axi_iic_0


class HeartOwner(JointOwner):
    def __init__(self,directory,hardware_factory=HeartHardware,lease=None,**kwargs):
        super().__init__(directory,hardware_factory,lease,**kwargs)

    def heart_ports(self):
        if self.state != "bound" or not self._hardware.is_loaded():
            raise RuntimeError("joint owner is not bound/current")
        return dict(iic=self._hardware.heart_iic(),nlms_mmio=self._io["nlms_axi_0"],
                    fifo_mmio=self._hardware.mmio("axi_fifo_mm_s_0"))


class JointBinding:
    """Session25's lease delegate; close only at its original release boundary."""
    def __init__(self,root,*,frozen_root=None,owner_factory=HeartOwner):
        self.root=Path(root).resolve()
        self.frozen=Path(frozen_root).resolve() if frozen_root else self.root/"frozen"
        self._factory=owner_factory
        self.owner=self.session=self.identity=self.cleanup=None
        self.prepare_calls=0
        self.prepare_error=self.release_error=None

    def prepare(self,base,output,*,hardware=False,release_contract=None):
        if hardware is not True:
            raise ValueError("joint preparation requires explicit hardware=True")
        if self.prepare_calls:
            raise RuntimeError("joint heart preparation already attempted; do not retry")
        self.prepare_calls+=1
        expected=self.frozen/"base/deps/static/checked/base"
        if Path(base).resolve()!=expected.resolve():
            raise ValueError("frozen runtime base does not match this package")
        from heart_v3a.live.board import _validated_bundle,validate_output
        from heart_v3a.live.contracts import LiveSettings
        from heart_v3a.axi_driver import NlmsAxiDriver
        from heart_axi_live import SensorBus,AxiFifoLoopback,pack_sample
        from effective25.session import Session25,SupervisedSource25
        from effective25.capture import Capture25
        from effective25.assessment import assess
        from effective25.policy import validate_registers,VERSION
        if release_contract is None:
            original_identity=_validated_bundle(base)
        else:
            from public_live_identity import check_runtime
            context=check_runtime(self.root,release_contract)
            original_identity=dict(base_manifest_sha256=context['manifest_sha256'],
                bit_sha256=None,hwh_sha256=None)
        output=validate_output(base,output)
        session=Session25(None,None,output,LiveSettings("baseline","static",60.))
        self.session=session
        session._claim_owner()
        session._board_lease=self
        try:
            self.owner=self._factory(self.root)
            self.identity=self.owner.open()
            ports=self.owner.heart_ports()
            backend=NlmsAxiDriver(ports["nlms_mmio"])
            nlms_identity=backend.identify()
            sensors=SensorBus(ports["iic"])
            sensor_ids=sensors.verify_identities()
            config=sensors.configure(fifo_sample_average=2,mpu_sample_rate_hz=25,mpu_dlpf_cfg=4)
            validate_registers(config)
            fifo=AxiFifoLoopback(ports["fifo_mmio"])
            fifo.reset()
            packet=pack_sample(0,0,0x12345,-1,2,-3)
            if fifo.round_trip(packet)!=packet:
                raise RuntimeError("joint heart FIFO startup loopback failed")
            session.source=SupervisedSource25(Capture25(sensors,fifo,protocol="static"),session)
            session.backend=backend
            session._overlay=self.owner
            session._hardware_authorized=True
            session._assess_summary=assess
            session._preflight=dict(base_manifest_sha256=original_identity["base_manifest_sha256"],
                bit_sha256=PAIR_HASHES["heart_v3b25.bit"],hwh_sha256=PAIR_HASHES["heart_v3b25.hwh"],
                frozen_reference_bit_sha256=original_identity["bit_sha256"],
                frozen_reference_hwh_sha256=original_identity["hwh_sha256"],
                joint_binding=True,joint_identity=self.identity,
                nlms_identity=nlms_identity,max30102_id=sensor_ids[0],mpu6050_id=sensor_ids[1],
                sensor_registers=config,fifo_startup_loopback_passed=True,limits_sha256=None,
                board_ddr_verified=False,schema=VERSION,adc_hz=50,raw_hz=25,processing_hz=25,
                fifo_sample_average=2,
                pairing_scope="latest_fifo_record_with_current_imu_not_hardware_synchronization")
            if release_contract is not None:
                session._preflight.update(release_manifest_sha256=context['manifest_sha256'],
                    historical_numerical_qualification=False,
                    validation_scope='public_live_runtime_assets_v1')
            return session
        except BaseException as exc:
            self.prepare_error=dict(type=type(exc).__name__,message=str(exc))
            try:
                session._release_owner()
            except BaseException as close_error:
                self.release_error=dict(type=type(close_error).__name__,message=str(close_error))
            raise

    def release(self):
        self.cleanup=self.owner.close() if self.owner is not None else dict(
            cleanup_complete=True,download_attempts=0,hardware_state="no_joint_owner_constructed")
        if not self.cleanup["cleanup_complete"]:
            raise RuntimeError("joint hardware cleanup not confirmed; do not retry")

    def report(self):
        return dict(prepare_calls=self.prepare_calls,joint_identity=self.identity,cleanup=self.cleanup,
                    prepare_error=self.prepare_error,release_error=self.release_error,
                    camera_started=False,hdmi_started=False,vision_frame_transferred=False)
