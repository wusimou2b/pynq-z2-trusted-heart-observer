"""Single final snapshot construction, using the unchanged frozen guard."""
from dataclasses import asdict
if __package__:
    from .joint_boundary import Probe
else:
    from joint_boundary import Probe


class SnapshotAdapter:
    def __init__(self):
        self.session=None
        self.installed=False
        self.restored=False

    def install(self,session):
        if self.installed:raise RuntimeError('snapshot adapter already installed')
        from heart_v3a.live.contracts import LiveSnapshot
        self.session=session
        self.present='snapshot' in vars(session)
        self.previous=vars(session).get('snapshot')
        def snapshot(*,now_ns=None):
            with session._lock:
                counts={**session._counts,**session._journal.counts()}
                state,fault,latest=session._state,session._fault,session._latest
                history=tuple(session._history)
                if latest is not None:
                    now=session.clock.monotonic_ns() if now_ns is None else now_ns
                    latest=session._guard_result(latest,now)
                counts['raw_safety']=asdict(session._safety.snapshot())
                counts['capture_loop_overruns']=session._overruns25
                return LiveSnapshot(state,fault,latest,history,counts)
        session.snapshot=snapshot
        self.installed=True

    def restore(self):
        if self.installed and not self.restored:
            if self.present:setattr(self.session,'snapshot',self.previous)
            else:delattr(self.session,'snapshot')
        self.restored=True

    def report(self):
        return dict(schema='v3b25_snapshot_adapter_v1',installed=self.installed,restored=self.restored,
            final_snapshot_constructions=1,original_guard_retained=True,status_cached=False)


class SnapshotProbe(Probe):
    """Keep original measurement and restore ordering around this one change."""
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.adapter=SnapshotAdapter()

    def install(self,session,video,mailbox):
        self.adapter.install(session)
        super().install(session,video,mailbox)

    def restore(self):
        super().restore()
        self.adapter.restore()

    def report(self):
        return dict(super().report(),snapshot_optimization=self.adapter.report())
