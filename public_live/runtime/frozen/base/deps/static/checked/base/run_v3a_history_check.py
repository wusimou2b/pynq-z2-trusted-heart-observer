"""板端只读历史检查等价/计时核对；不导入PYNQ、不加载Overlay。"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np
import scipy
from heart_v3a.live.numpy_compat import assess_history as frozen_assess, CompatibleJointBenefitSelector
from heart_v3a.live.history_fast import assess_history as fast_assess, FastJointBenefitSelector


def window_cases():
    t = np.arange(200)/50.
    pulse, motion = np.sin(2*np.pi*1.2*t), np.sin(2*np.pi*2.1*t)
    source = np.column_stack((np.arange(200), pulse+.7*motion, pulse+.1*motion,
        motion, motion, .4*motion, -.2*motion, pulse+.7*motion))
    cases = []
    for name in ("ordinary", "independent_actual", "inactive", "one_axis", "candidate_low", "actual_low",
                 "actual_motion", "constant", "zero", "small", "reversed", "wide_stride"):
        data = source.copy()
        if name == "independent_actual": data[:,7] = pulse+.3*motion
        if name == "inactive": data[:,4:7] = 0.
        if name == "one_axis": data[:,5:7] = 0.
        if name == "candidate_low": data[:,2] *= .01
        if name == "actual_low": data[:,7] *= .01
        if name == "actual_motion": data[:,7] = motion
        if name == "constant": data[:,1:] = 1.
        if name == "zero": data[:,1:] = 0.
        if name == "small": data[:,1:] *= 1e-7
        if name == "reversed": data = data[::-1]
        if name == "wide_stride": data = np.repeat(data, 3, axis=0)[::3]
        cases.append((name, (data[:,1], data[:,2], data[:,3], data[:,4:7], data[:,7])))
    return cases


def differing_field(actual, expected):
    for key, value in asdict(expected).items():
        got = getattr(actual, key)
        if isinstance(value, np.ndarray):
            equal = got.dtype == value.dtype and np.array_equal(got, value, equal_nan=True)
        elif isinstance(value, float):
            equal = float(got).hex() == value.hex()
        else:
            equal = got == value
        if not equal:
            return key
    return None


def check():
    cases = window_cases()
    differences = 0
    first = None
    for name, values in cases:
        field = differing_field(fast_assess(*values), frozen_assess(*values))
        if field:
            differences += 1
            first = first or dict(stage="window", case=name, field=field)
    fast, frozen = FastJointBenefitSelector(), CompatibleJointBenefitSelector()
    requested = checks = 0
    for i in range(700):
        t = i/50.
        pulse, motion = np.sin(2*np.pi*1.2*t), np.sin(2*np.pi*2.1*t)
        candidate = pulse+.1*motion if i < 320 or i >= 410 else .01*(pulse+.7*motion)
        values = pulse+.7*motion, candidate, motion, (motion, .4*motion, -.2*motion)
        flags = dict(reset=i == 410, valid=i != 660, contact_allowed=i != 665, clipped=i == 670)
        actual, expected = fast.step(*values, **flags), frozen.step(*values, **flags)
        field = differing_field(actual, expected)
        if not field and (tuple(fast.history) != tuple(frozen.history) or fast.index != frozen.index):
            field = "history_or_index"
        if field:
            differences += 1
            first = first or dict(stage="selector", index=i, field=field)
        checks += expected.checked
        requested += expected.requested
    timing = None
    if differences == 0:
        # 只计时同样四组真实计算输入；交替次序，计时不混入cProfile。
        selected = [cases[i][1] for i in (0, 1, 10, 11)]
        durations = {"frozen": [], "fast": []}
        for repeat in range(3):
            for name in (("frozen", "fast") if repeat % 2 == 0 else ("fast", "frozen")):
                function = frozen_assess if name == "frozen" else fast_assess
                for values in selected:
                    started = time.perf_counter_ns()
                    function(*values)
                    durations[name].append((time.perf_counter_ns()-started)/1e6)
        old, new = (statistics.median(durations[name]) for name in ("frozen", "fast"))
        timing = dict(frozen_median_ms=old, fast_median_ms=new, speedup=old/new,
            per_window_ms=durations, scope_cn="仅原/新历史检查，不是PL、全链、采集或配对验收")
    return dict(schema="v3a_history_check_v1", python=sys.version, numpy=np.__version__,
        scipy=scipy.__version__, machine=platform.machine(), exact_equivalence_passed=differences == 0,
        windows_compared=len(cases), selector_samples=700, selector_checks=checks,
        requested_samples=requested, differences=differences, first_difference=first, timing=timing,
        hardware_loaded=False, live_50hz_passed=False, board_ddr_verified=False,
        auto_beta_effect_passed=False, v3a_complete=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.output is not None and args.output.exists():
        raise FileExistsError("不覆盖已有只读核对报告：" + str(args.output))
    report = check()
    if args.output is not None:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["exact_equivalence_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
