"""隔离的运行时β整数对照；复用冻结数值原语，默认逐字段一致。"""
from dataclasses import replace
from .fixed_nlms import (FixedNlms4, FixedNlmsStep, BETA_INT, EPSILON_INT,
    WEIGHT_LIMIT_INT, WEIGHT_BITS, WEIGHT_FRACTION, ZERO_STATE,
    _ArithmeticSaturation, _signed, _unsigned, _empty_step)
from .fixed_math import round_ratio, round_shift


class RuntimeFixedNlms4(FixedNlms4):
    def step_int(self, desired: int, references: tuple[int, int, int], *,
                 beta_int: int = BETA_INT, valid: bool = True, update: bool = True,
                 reset: bool = False, bypass: bool = False) -> FixedNlmsStep:
        if type(beta_int) is not int or not 1 <= beta_int <= (1 << 30):
            raise ValueError('beta_int必须为1到1073741824之间的整数')
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
            proposed = tuple(tuple(w + round_ratio(_signed(beta_int*error*x, 96), denominator)
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

