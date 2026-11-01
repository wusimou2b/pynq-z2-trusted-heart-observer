"""板端只读单点 SOS 等价／计时核对；不加载 Overlay，不访问传感器。"""
import argparse
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
import time

import numpy as np
import scipy
from heart_v2.heartrate import CausalHeartRateDetector
from heart_v2.runtime_main_chain import runtime_config
from heart_v3a.live.single_sample import ScalarSosHeartRateDetector


def state(detector):
    """包含全部冻结可变状态；字节／hex 比较，不用近似容差。"""
    return (detector.sos.tobytes(), detector.zi.tobytes(),
        detector.previous_previous.hex(), detector.previous.hex(), detector.envelope.hex(),
        detector.previous_previous_trusted, detector.previous_trusted, detector.sample_index,
        detector.last_peak_index, detector.accepted_peak_count,
        tuple(detector.ibis), detector.ibis.maxlen)


def check(samples):
    parameters = runtime_config()["heartrate"]
    rng = random.Random(2108)
    noise = [rng.uniform(-1., 1.) for _ in range(samples)]
    compared = differences = trusted = resets = 0
    first_difference = None
    for case in ("flat", "impulse", "pulse", "mixed", "noise", "large"):
        frozen = CausalHeartRateDetector(50., **parameters)
        scalar = ScalarSosHeartRateDetector(50., **parameters)
        for index in range(samples):
            t = index / 50.
            value = {"flat": 0., "impulse": float(index in (0, samples // 2 + 1)),
                "pulse": math.sin(2 * math.pi * 1.2 * t),
                "mixed": 2 * math.sin(2 * math.pi * .7 * t) + math.cos(2 * math.pi * 3 * t),
                "noise": noise[index], "large": 1e8 * math.sin(2 * math.pi * 1.2 * t)}[case]
            allowed = not (samples // 5 <= index < samples // 5 + 30)
            if index in (samples // 2, 3 * samples // 4):
                frozen.reset(); scalar.reset()
                resets += 1
                if state(frozen) != state(scalar):
                    differences += 1
                    if first_difference is None:
                        first_difference = dict(case=case, index=index, stage="reset")
            expected = frozen.step(value, allowed)
            actual = scalar.step(value, allowed)
            compared += 1
            trusted += expected.trusted
            if (actual != expected or actual.filtered.hex() != expected.filtered.hex()
                    or state(scalar) != state(frozen)):
                differences += 1
                if first_difference is None:
                    first_difference = dict(case=case, index=index, stage="step")

    timing = None
    if differences == 0:
        # 仅 detector.step；输入提前生成，无 cProfile、软件 NLMS、显示或 I/O 混入。
        values = [math.sin(2 * math.pi * 1.2 * index / 50.) for index in range(samples)]
        durations = {"frozen": [], "scalar": []}
        for repeat in range(3):
            order = ("frozen", "scalar") if repeat % 2 == 0 else ("scalar", "frozen")
            for name in order:
                kind = CausalHeartRateDetector if name == "frozen" else ScalarSosHeartRateDetector
                instance = kind(50., **parameters)
                started = time.perf_counter()
                for value in values:
                    instance.step(value, True)
                durations[name].append(1000 * (time.perf_counter() - started) / samples)
        old, new = (statistics.median(durations[name]) for name in ("frozen", "scalar"))
        timing = dict(frozen_median_ms=old, scalar_median_ms=new,
            speedup=old / new, per_sample_runs_ms=durations,
            scope_cn="仅判峰器逐样本执行，不是全链、PL延迟或50Hz配对验收")
    return dict(schema="v3a_single_sample_check_v1", python=sys.version,
        numpy=np.__version__, scipy=scipy.__version__, machine=platform.machine(),
        exact_equivalence_passed=differences == 0, samples_compared=compared,
        state_differences=differences, first_difference=first_difference,
        trusted_bpm_samples=trusted, resets_checked=resets, timing=timing,
        hardware_loaded=False, live_50hz_passed=False, board_ddr_verified=False,
        auto_beta_effect_passed=False, v3a_complete=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=1500)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.samples < 400:
        parser.error("至少400点，才能覆盖可信心率及重置恢复")
    if args.output is not None and args.output.exists():
        raise FileExistsError("不覆盖已有只读核对报告：" + str(args.output))
    report = check(args.samples)
    if args.output is not None:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["exact_equivalence_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
