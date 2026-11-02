"""Frozen hardware preparation, followed by mandatory raw safety rebinding."""
from pathlib import Path
from .delivery import validate, digest


def prepare(root, capture, *, hardware=False):
    if hardware is not True: raise ValueError('必须显式hardware=True')
    root = Path(root).resolve()
    validate(root)
    from heart_v3a.live.board import prepare_live_session
    from heart_v3a.live.contracts import LiveSettings
    from v3a_25hz_live.session import LiveSession25, _SupervisedSource
    from .assessment import assess
    session = prepare_live_session(root/'checked/base',capture,LiveSettings('baseline','static',60.),
                                   hardware=True,session_factory=LiveSession25)
    try:
        # Frozen preparation replaces source. Restore raw safety before start().
        session.source = _SupervisedSource(session.source,session)
        session._assess_summary = assess
        session._preflight.update(raw_hz=50,processing_hz=25,
            pilot25_manifest_sha256=digest(root/'pilot25-manifest.json'),
            checked_manifest_sha256=digest(root/'checked/manifest25.json'))
        return session
    except BaseException:
        session._release_owner()
        raise
