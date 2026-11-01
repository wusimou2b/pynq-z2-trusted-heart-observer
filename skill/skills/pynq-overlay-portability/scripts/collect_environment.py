"""Collect software metadata only; never import pynq or instantiate a Device."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import platform


def collect():
    try:
        version = importlib.metadata.version('pynq')
    except importlib.metadata.PackageNotFoundError:
        version = None
    return {'schema': 'pynq-environment-v1', 'pynq_version': version,
            'python_version': platform.python_version(), 'os': platform.system(),
            'machine': platform.machine(), 'hardware_accessed': False,
            'device_detected': False, 'driver_binding_verified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if Path(args.output).exists():
        parser.error('output exists')
    with Path(args.output).open('x', encoding='utf8') as stream:
        json.dump(collect(), stream, indent=2)
