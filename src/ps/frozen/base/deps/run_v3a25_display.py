"""Default read-only bundle check. Hardware display runs only in Notebook."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT),str(ROOT/'static'),str(ROOT/'static/checked'),str(ROOT/'static/checked/base')]


def run_display60(*,hardware=False,output=None):
    from display25.runner import run
    return run(ROOT,output,hardware=hardware)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle',action='store_true')
    parser.parse_args()
    from display25.delivery import validate,FLAGS
    validate(ROOT)
    print(json.dumps(dict(bundle_validated=True,raw_hz=50,processing_hz=25,
        entry='notebook_display60',hardware_loaded=False,**FLAGS)))
    return 0


if __name__ == '__main__': raise SystemExit(main())
