"""只给新live绑定旧NumPy积分名字；冻结函数代码及全局模块保持不动。"""
from functools import update_wrapper
from types import FunctionType

import numpy as np

from heart_v2 import aligned_metrics as frozen_metrics
from heart_v2 import joint_benefit as frozen_selector
from heart_v3a.runtime_pl_chain import RuntimePlMainChain


class _IntegralApi:
    """只读视图：缺少新名字时使用旧版原生trapz，绝不修改NumPy。"""

    def __getattr__(self, name):
        try:
            return getattr(np, name)
        except AttributeError:
            if name != "trapezoid":
                raise
            return np.trapz


def _bind(function, **dependencies):
    """共享原code对象，仅隔离其globals查找；保留默认值及关键字默认值。"""
    bound = FunctionType(function.__code__, {**function.__globals__, **dependencies},
        function.__name__, function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = None if function.__kwdefaults__ is None else dict(function.__kwdefaults__)
    return update_wrapper(bound, function)


# 不复制公式、阈值、谱段或选路规则；整条私有查找链执行原代码。
band_power = _bind(frozen_metrics.band_power, np=_IntegralApi())
aligned_metrics = _bind(frozen_metrics.aligned_metrics, band_power=band_power)
assess_history = _bind(frozen_selector.assess_history, aligned_metrics=aligned_metrics)


class CompatibleJointBenefitSelector(frozen_selector.JointBenefitSelector):
    step = _bind(frozen_selector.JointBenefitSelector.step, assess_history=assess_history)


# 原step在控制变化时会重建选择器；这条私有绑定防止退回不兼容的旧实例。
runtime_step = _bind(RuntimePlMainChain.step, JointBenefitSelector=CompatibleJointBenefitSelector)
