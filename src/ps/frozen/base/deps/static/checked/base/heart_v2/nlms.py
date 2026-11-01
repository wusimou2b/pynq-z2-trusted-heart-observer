"""隔离的归一化自适应滤波开发模型。"""

from dataclasses import dataclass
import numpy as np


EPSILON = .001
ENERGY_FLOOR = 1e-6
ERROR_ALPHA = .02
WARMUP_SAMPLES = 50
OUTLIER_MULTIPLIER = 6.
BASELINE_FLOOR = .001
INCREMENT_LIMIT = .02
BETA_CANDIDATES = (.001, .003, .01, .03, .1)


@dataclass(frozen=True)
class NlmsStep:
    estimate: float
    error: float
    weights: np.ndarray
    clipped: bool
    energy: float
    increment_norm: float
    effective_gain: float
    increment_limited: bool
    skip_reason: str
    baseline_before: float
    error_outlier: bool


class Nlms4:
    """每轴四抽头，先输出后更新；保护只约束学习，不旁路输出。"""

    def __init__(self, beta, channels=3, protected=False, weight_limit=8., epsilon=EPSILON):
        if (not np.isfinite(beta) or beta <= 0 or not np.isfinite(weight_limit)
                or weight_limit <= 0 or not np.isfinite(epsilon) or epsilon <= 0
                or not isinstance(channels, int) or isinstance(channels, bool) or channels < 1):
            raise ValueError('invalid NLMS parameters')
        self.beta, self.channels = float(beta), channels
        self.protected = bool(protected)
        self.weight_limit, self.epsilon = float(weight_limit), float(epsilon)
        self.reset()

    def reset(self):
        self.weights = np.zeros((self.channels, 4))
        self.reference_state = np.zeros_like(self.weights)
        self.error_baseline = 0.
        self.observed_samples = 0

    def step(self, desired, reference, update=True):
        reference = np.asarray(reference, float)
        if (np.ndim(desired) != 0 or reference.shape != (self.channels,)
                or not np.isfinite(reference).all() or not np.isfinite(desired)):
            raise ValueError('invalid NLMS sample')
        # 局部计算完成后提交状态；拒绝非法样本不污染后续历史。
        state = np.empty_like(self.reference_state)
        state[:, 1:] = self.reference_state[:, :-1]
        state[:, 0] = reference
        energy = float(np.sum(state * state))
        estimate = float(np.sum(self.weights * state))
        error = float(desired) - estimate
        baseline = self.error_baseline
        outlier = bool(self.protected and self.observed_samples >= WARMUP_SAMPLES
                       and abs(error) > OUTLIER_MULTIPLIER * max(baseline, BASELINE_FLOOR))
        reason = ('external_mask' if not update else
                  'low_energy' if self.protected and energy < ENERGY_FLOOR else
                  'error_outlier' if outlier else '')
        gain = 0. if reason else self.beta / (self.epsilon + energy)
        increment = gain * error * state
        limited = False
        proposed_norm = float(np.linalg.norm(increment))
        if self.protected and proposed_norm > INCREMENT_LIMIT:
            scale = INCREMENT_LIMIT / proposed_norm
            increment *= scale
            gain *= scale
            limited = True
        candidate = self.weights + increment
        clipped = bool(np.any(np.abs(candidate) > self.weight_limit))
        weights = np.clip(candidate, -self.weight_limit, self.weight_limit)
        if not (np.isfinite(energy) and np.isfinite(estimate) and np.isfinite(error)
                and np.isfinite(gain) and np.isfinite(weights).all()):
            raise ValueError('nonfinite NLMS computation')
        increment_norm = float(np.linalg.norm(weights - self.weights))
        self.reference_state, self.weights = state, weights
        # 外部冻结不冻结误差观察；异常点不进入基线，先判定再更新。
        if not outlier:
            self.error_baseline = (abs(error) if self.observed_samples == 0 else
                                   (1 - ERROR_ALPHA) * baseline + ERROR_ALPHA * abs(error))
        self.observed_samples += 1
        return NlmsStep(estimate, error, weights.copy(), clipped, energy,
                        increment_norm, gain, limited, reason, baseline, outlier)


@dataclass(frozen=True)
class Replay:
    output: np.ndarray
    weights: np.ndarray
    clipped: np.ndarray
    energy: np.ndarray
    increment_norm: np.ndarray
    effective_gain: np.ndarray
    increment_limited: np.ndarray
    skip_reason: np.ndarray
    baseline_before: np.ndarray
    error_outlier: np.ndarray
    estimate: np.ndarray


def replay(desired, references, reset, update, valid, beta, protected=False, weight_limit=8.):
    """延迟固定为零；无效样本与阶段重置均清除全部学习状态。"""
    desired, references = np.asarray(desired, float), np.asarray(references, float)
    if desired.ndim != 1:
        raise ValueError('invalid desired shape')
    n = len(desired)
    if (references.ndim != 2 or len(references) != n
            or any(np.asarray(m).shape != (n,) for m in (reset, update, valid))):
        raise ValueError('invalid replay shapes')
    reset, update, valid = (np.asarray(m, bool) for m in (reset, update, valid))
    if not (np.isfinite(desired[valid]).all() and np.isfinite(references[valid]).all()):
        raise ValueError('nonfinite valid samples')
    filt = Nlms4(beta, references.shape[1], protected, weight_limit)
    fields = {k: np.zeros(n) for k in ('output', 'energy', 'increment_norm', 'effective_gain',
                                      'baseline_before', 'estimate')}
    fields.update({k: np.zeros(n, bool) for k in ('clipped', 'increment_limited', 'error_outlier')})
    fields['skip_reason'] = np.full(n, 'invalid', dtype='<U20')
    fields['weights'] = np.zeros((n, references.shape[1], 4))
    for i in range(n):
        if reset[i] or not valid[i]:
            filt.reset()
        if not valid[i]:
            continue
        step = filt.step(desired[i], references[i], bool(update[i]))
        fields['output'][i] = step.error
        for k in fields:
            if k != 'output':
                fields[k][i] = getattr(step, k)
    return Replay(**fields)


def candidate_eligible(row):
    values = [row[k] for k in ('output_rms_ratio', 'pulse_band_power_ratio', 'motion_leakage_reduction_db')]
    return bool(row['finite'] and np.isfinite(values).all() and row['clipped_samples'] == 0
                and row['output_rms_ratio'] >= .4 and row['pulse_band_power_ratio'] >= .5)


def select_candidate(rows):
    eligible = [r for r in rows if candidate_eligible(r)]
    return min(eligible, key=lambda r: (-r['motion_leakage_reduction_db'], r['beta'])) if eligible else None
