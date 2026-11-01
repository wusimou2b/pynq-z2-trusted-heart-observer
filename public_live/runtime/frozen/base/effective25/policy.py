"""Physical-time conversion; neither old configuration nor algorithm is mutated."""
from heart_v2.runtime_main_chain import runtime_config

VERSION = 'effective25_process25_v1'
ADC_HZ = 50
SAMPLE_AVERAGE = 2
RAW_HZ = PROCESS_HZ = 25
PERIOD_US = 40000
MAX_GAP_SECONDS = .08
ACCEL_REPEAT_LIMIT = 50


def contact_config():
    config = runtime_config()['contact']
    config['amplitude_window_samples'] = 50
    config['recovery_samples'] = 25
    config['baseline_alpha'] = 1-(1-config['baseline_alpha'])**2
    return config


def expected_registers():
    return dict(fifo_config=0x2F, spo2_config=0x23, mode_config=3,
                mpu_sample_rate_divider=39, mpu_dlpf_config=4, mpu_accel_config=0)


def validate_registers(actual):
    for name, value in expected_registers().items():
        if type(actual.get(name)) is not int or actual[name] != value:
            raise ValueError('25Hz寄存器读回不符：'+name)
    return True
