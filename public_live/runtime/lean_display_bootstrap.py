"""Validate the original frozen tree, without importing its PS calculation target.

Only the Notebook/controller uses this entry. Calculation and hardware workers
retain load_original/load_chain and their original identity and warmup checks.
"""
from pathlib import Path
import sys


def activate_display(frozen):
    frozen = Path(frozen).resolve(strict=True)
    if str(frozen) not in sys.path:
        sys.path.insert(0, str(frozen))
    import entry25_guard
    if Path(entry25_guard.__file__).resolve() != frozen / 'entry25_guard.py':
        raise RuntimeError('mixed display entry guard')
    # Same complete validation and mixed-module rejection as load_original.
    entry25_guard.validate(frozen)
    entry25_guard.activate(frozen)
    paths = (frozen / 'base/deps', frozen / 'base/deps/static',
             frozen / 'base/deps/static/checked',
             frozen / 'base/deps/static/checked/base')
    for path in reversed(paths):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    return entry25_guard.identity(frozen)


def load_display_runtime(frozen):
    identity = activate_display(frozen)
    from owner25 import transport
    from v3a_25hz_live.view import LiveView25
    from browser_heart_display import BrowserRenderer
    from display_copy_transport import CopyMailbox
    return identity, transport, LiveView25, BrowserRenderer, CopyMailbox
