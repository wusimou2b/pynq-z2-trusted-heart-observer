"""固定三轴×四抽头限幅NLMS；数值契约供后续RTL逐拍对照。"""
from dataclasses import dataclass, replace

from .fixed_math import clip_signed, round_ratio, round_shift

SIGNAL_BITS = 24
SIGNAL_FRACTION = 16
WEIGHT_BITS = 24
WEIGHT_FRACTION = 18
BETA_INT = 32212255
EPSILON_INT = 4294967
WEIGHT_LIMIT_INT = 8 << WEIGHT_FRACTION
ZERO_STATE = ((0, 0, 0, 0),) * 3


@dataclass(frozen=True)
class FixedNlmsStep:
    desired_int: int
    reference_ints: tuple[int, int, int]
    estimate_int: int
    error_int: int
    energy_int: int
    candidate_int: int
    output_int: int
    weight_ints: tuple[tuple[int, ...], ...]
    history_ints: tuple[tuple[int, ...], ...]
    output_valid: bool
    update_applied: bool
    weight_clipped: bool
    arithmetic_saturated: bool


class _ArithmeticSaturation(Exception):
    """不可将宽运算回绕或饱和值当成有效输出。"""


def _signed(value, bits):
    word = clip_signed(value, bits)
    if word.saturated:
        raise _ArithmeticSaturation
    return word.value


def _unsigned(value, bits):
    if not 0 <= value < 1 << bits:
        raise _ArithmeticSaturation
    return value


def _empty_step():
    return FixedNlmsStep(0, (0, 0, 0), 0, 0, 0, 0, 0, ZERO_STATE,
        ZERO_STATE, False, False, False, False)


class FixedNlms4:
    def __init__(self):
        self.weight_clipped_samples = 0
        self.arithmetic_saturated_samples = 0
        self.reset()

    def reset(self, *, clear_counters: bool = False) -> None:
        if type(clear_counters) is not bool:
            raise ValueError('clear_counters必须为bool')
        self._weights = self._history = ZERO_STATE
        if clear_counters:
            self.weight_clipped_samples = self.arithmetic_saturated_samples = 0

    def step_int(self, desired: int, references: tuple[int, int, int], *,
                 valid: bool = True, update: bool = True,
                 reset: bool = False, bypass: bool = False) -> FixedNlmsStep:
        # 在清状态或累计计数之前，先拒绝所有非法控制与有效载荷。
        if any(type(flag) is not bool for flag in (valid, update, reset, bypass)):
            raise ValueError('valid／update／reset／bypass必须为bool')
        if not valid:
            self.reset()
            return _empty_step()
        if not isinstance(references, (tuple, list)) or len(references) != 3:
            raise ValueError('参考载荷必须为三轴整数')
        if any(type(value) is not int or not -(1 << 23) <= value < (1 << 23)
               for value in (desired, *references)):
            raise ValueError('有效载荷必须为24位有符号整数，不允许bool')
        references = tuple(references)
        old_weights = ZERO_STATE if reset else self._weights
        old_history = ZERO_STATE if reset else self._history
        history = tuple((value,) + old[:3] for value, old in zip(references, old_history))
        try:
            energy = _unsigned(EPSILON_INT + sum(x*x for axis in history for x in axis), 52)
            denominator = _unsigned(energy << 12, 64)
            products = [_signed(w*x, 48) for wa, ha in zip(old_weights, history)
                        for w, x in zip(wa, ha)]
            # 全精度累加后一次缩位；不逐项缩位或饱和MAC。
            mac = _signed(sum(products), 52)
            estimate = _signed(round_shift(mac, WEIGHT_FRACTION), 40)
            error = _signed(desired - estimate, 40)
            proposed = tuple(tuple(w + round_ratio(_signed(BETA_INT*error*x, 96), denominator)
                if update else w for w, x in zip(wa, ha)) for wa, ha in zip(old_weights, history))
            clipped = any(abs(w) > WEIGHT_LIMIT_INT for axis in proposed for w in axis)
            weights = tuple(tuple(_signed(max(-WEIGHT_LIMIT_INT, min(WEIGHT_LIMIT_INT, w)), WEIGHT_BITS)
                for w in axis) for axis in proposed)
            bound = abs(desired)//2
            candidate = _signed(desired - max(-bound, min(bound, estimate)), 32)
            output = _signed(desired if bypass else candidate, 32)
        except _ArithmeticSaturation:
            self.arithmetic_saturated_samples += 1
            self.reset()
            return replace(_empty_step(), arithmetic_saturated=True)
        # 只有完整合法计算才能提交新状态；本拍输出使用旧权重。
        self._weights, self._history = weights, history
        self.weight_clipped_samples += int(clipped)
        return FixedNlmsStep(desired, references, estimate, error, energy,
            candidate, output, weights, history, True, update, clipped, False)
