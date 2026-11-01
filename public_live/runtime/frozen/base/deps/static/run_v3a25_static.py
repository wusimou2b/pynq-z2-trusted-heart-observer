"""Fixed 60s static raw50/process25 pilot; no default hardware action."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT),str(ROOT/'checked'),str(ROOT/'checked/base')]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check-bundle',action='store_true')
    mode.add_argument('--static60',action='store_true')
    parser.add_argument('--hardware',action='store_true')
    parser.add_argument('--output',type=Path)
    args = parser.parse_args(argv)
    if args.static60 != args.hardware: parser.error('--static60和--hardware必须同时明确提供')
    from pilot25.delivery import validate,FLAGS
    validate(ROOT)
    if not args.static60:
        print(json.dumps(dict(bundle_validated=True,raw_hz=50,processing_hz=25,hardware_loaded=False,**FLAGS)))
        return 0
    from pilot25.runner import run
    report = run(ROOT,args.output,hardware=True)
    if report['error'] and report['error']['type'] == 'KeyboardInterrupt': return 130
    return 0 if report['static_pilot_completed'] else 1


if __name__ == '__main__': raise SystemExit(main())
