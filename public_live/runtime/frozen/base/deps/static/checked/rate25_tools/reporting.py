import json
import math
from pathlib import Path
import platform
import statistics
import sys
from datetime import datetime
import uuid

from .delivery import FLAGS, digest


def output_directory(root, output, prefix):
    root = Path(root).resolve()
    path = (Path(output).resolve() if output is not None else
            root/'checks'/(prefix+'-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]))
    if path.is_relative_to(root) and (path == root or path.relative_to(root).parts[0] != 'checks'):
        raise ValueError('包内输出只允许checks下的新目录')
    path.mkdir(parents=True, exist_ok=False)
    return path


def save(directory, filename, report):
    with (Path(directory)/filename).open('x', encoding='utf8') as stream:
        json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)


def header(root, schema):
    return dict(schema=schema, **FLAGS, manifest25_sha256=digest(Path(root)/'manifest25.json'),
                python=sys.version, executable=sys.executable, machine=platform.machine(),
                platform=platform.platform(), error=None)


def distribution(values):
    if not values: return dict(count=0,mean_ms=None,median_ms=None,p99_ms=None,max_ms=None)
    ordered = sorted(values)
    position = (len(ordered)-1)*.99
    lo, hi = math.floor(position), math.ceil(position)
    p99 = ordered[lo]+(ordered[hi]-ordered[lo])*(position-lo)
    return dict(count=len(values),mean_ms=statistics.mean(values)/1e6,
                median_ms=statistics.median(values)/1e6,p99_ms=p99/1e6,max_ms=max(values)/1e6)
