"""Versioned physical-time conversion; old 50 Hz configuration is read-only."""
from heart_v2.runtime_main_chain import runtime_config

VERSION = 'raw50_process25_v1'
RAW_HZ = 50
PROCESS_HZ = 25
HISTORY = 100
CHECK_EVERY = 5
MOTION_WINDOW = 25
MEAN_WINDOW = 2
MAX_PEAK_AGE_SECONDS = 1.5
PERIOD_LAGS = range(8,38)
CORRELATION_LAG = 5
MIX_STEP = .2
COOLDOWN = 25


def configuration():
    config = runtime_config()
    config['sample_rate_hz'] = PROCESS_HZ
    for name in ('ppg_dc_alpha','reference_dc_alpha'):
        config['preprocess'][name] **= 2
    alpha = config['heartrate']['threshold_alpha']
    config['heartrate']['threshold_alpha'] = 1-(1-alpha)**2
    return config


def peak_fresh(age):
    return age is not None and 0 <= age/PROCESS_HZ <= MAX_PEAK_AGE_SECONDS
