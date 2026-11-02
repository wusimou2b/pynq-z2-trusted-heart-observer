"""整数定点原语：半数远离零、显式饱和、不经浮点中间运算。"""
from dataclasses import dataclass
import math
from numbers import Real


@dataclass(frozen=True)
class Word:
    value: int
    saturated: bool


def round_ratio(numerator: int, denominator: int) -> int:
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise ValueError('整数分子与正整数分母必需')
    quotient, remainder = divmod(abs(numerator), denominator)
    rounded = quotient + int(2 * remainder >= denominator)
    return -rounded if numerator < 0 else rounded


def round_shift(value: int, shift: int) -> int:
    if type(value) is not int or type(shift) is not int:
        raise ValueError('移位参数必须是整数')
    return round_ratio(value, 1 << shift) if shift >= 0 else value << -shift


def clip_signed(value: int, bits: int) -> Word:
    if type(value) is not int or type(bits) is not int or bits < 2:
        raise ValueError('非法有符号格式')
    bounded = max(-(1 << (bits - 1)), min(value, (1 << (bits - 1)) - 1))
    return Word(bounded, bounded != value)


def quantize(value: float, bits: int, fraction_bits: int) -> Word:
    if (type(bits) is not int or bits < 2 or type(fraction_bits) is not int
            or not 0 <= fraction_bits < bits or isinstance(value, bool)
            or not isinstance(value, Real)):
        raise ValueError('量化需要有限实数与合法位宽／小数位')
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError('量化输入不能表示为有限实数') from exc
    if not math.isfinite(value):
        raise ValueError('量化输入必须是有限实数')
    numerator, denominator = value.as_integer_ratio()
    return clip_signed(round_ratio(numerator << fraction_bits, denominator), bits)
