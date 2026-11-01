"""25Hz independent bundle checks. Default action never loads an Overlay."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT/'base'), str(ROOT)]


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    modes = result.add_mutually_exclusive_group()
    modes.add_argument('--check-bundle', action='store_true')
    modes.add_argument('--budget', action='store_true')
    modes.add_argument('--pl-replay', action='store_true')
    result.add_argument('--hardware', action='store_true')
    result.add_argument('--output', type=Path)
    return result


def main(argv=None):
    options = parser()
    args = options.parse_args(argv)
    if args.hardware != args.pl_replay:
        options.error('--pl-replay 与 --hardware 必须一起使用；只读测量不能带 --hardware')
    from rate25_tools.delivery import validate, FLAGS
    validate(ROOT)
    if args.budget:
        print('只读预算：不放手指，不加载Overlay，不同时运行采集或绘图。', flush=True)
        from rate25_tools.budget import run
        report = run(ROOT, args.output)
        return 0 if report['budget_report_complete'] else 1
    if args.pl_replay:
        from rate25_tools.hardware import run
        report = run(ROOT, args.output, hardware=True)
        return 0 if report['board_pl25_replay_passed'] else 1
    print(json.dumps(dict(bundle_validated=True, raw_hz=50, processing_hz=25, **FLAGS), ensure_ascii=False))
    return 0


if __name__ == '__main__': raise SystemExit(main())
