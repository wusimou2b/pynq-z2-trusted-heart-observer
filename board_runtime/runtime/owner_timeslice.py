"""Experimental owner-process-only GIL interval; no live installation yet."""
from contextlib import contextmanager
import math
import sys

@contextmanager
def owner_timeslice(seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=.005:
        raise ValueError('bounded owner thread interval required')
    before=sys.getswitchinterval()
    try:
        sys.setswitchinterval(seconds)
        yield
    finally:
        sys.setswitchinterval(before)
