"""Preserve frozen Overlay/lease checks; reconfigure BEFORE start and startup discard."""
from .policy import validate_registers, VERSION


def prepare(base,output,*,hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    from heart_v3a.live.board import prepare_live_session
    from heart_v3a.live.contracts import LiveSettings
    from .session import Session25, SupervisedSource25
    from .capture import Capture25
    from .assessment import assess
    # Frozen setup briefly configures raw50 for its original identity checks.
    # No capture thread starts there. All formal data starts AFTER this override,
    # new register readback, worker warmup and original FIFO startup discard.
    session=prepare_live_session(base,output,LiveSettings('baseline','static',60.),
                                 hardware=True,session_factory=Session25)
    try:
        original=session.source
        config=original.sensors.configure(fifo_sample_average=2,mpu_sample_rate_hz=25,mpu_dlpf_cfg=4)
        validate_registers(config)
        session.source=SupervisedSource25(Capture25(original.sensors,original.fifo,protocol='static'),session)
        session._assess_summary=assess
        session._preflight.update(schema=VERSION,sensor_registers=config,adc_hz=50,
            raw_hz=25,processing_hz=25,fifo_sample_average=2,
            pairing_scope='latest_fifo_record_with_current_imu_not_hardware_synchronization')
        return session
    except BaseException:
        session._release_owner()
        raise
