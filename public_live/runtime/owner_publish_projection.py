"""Owner-only display projection; retain full history and every safety read.

Full counters remain in the Session and journal. Non-owner calls, stopping,
and finalization use the retained complete snapshot. No publication caching,
new timing interval, new IPC format, or modified processing method.
"""
from contextlib import contextmanager
from dataclasses import asdict
import threading


@contextmanager
def publication_projection(session):
    from heart_v3a.live.contracts import LiveSnapshot
    owner=threading.get_ident();previous=session.snapshot
    present='snapshot' in vars(session)
    def snapshot(*,now_ns=None):
        if threading.get_ident()!=owner:return previous(now_ns=now_ns)
        with session._lock:
            if session._state!='running':return previous(now_ns=now_ns)
            state,fault,latest=session._state,session._fault,session._latest
            history=tuple(session._history)
            if latest is not None:
                now=session.clock.monotonic_ns() if now_ns is None else now_ns
                latest=session._guard_result(latest,now)
            # This is the same second safety observation as SnapshotAdapter;
            # changes during _guard_result must remain visible to consumers.
            safety=asdict(session._safety.snapshot())
            return LiveSnapshot(state,fault,latest,history,{'raw_safety':safety})
    session.snapshot=snapshot
    try:yield
    finally:
        if getattr(session,'snapshot',None) is snapshot:
            if present:session.snapshot=previous
            else:del session.snapshot
