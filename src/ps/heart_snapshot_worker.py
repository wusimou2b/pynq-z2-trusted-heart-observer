"""Heart-only instance adapter; original owner/GC/PS lifecycle remains in charge."""
import json
import os
from pathlib import Path

if __package__:
    from .joint_heart_binding import JointBinding
    from .joint_snapshot import SnapshotAdapter
else:
    from joint_heart_binding import JointBinding
    from joint_snapshot import SnapshotAdapter


def describe(exc):
    return dict(type=type(exc).__name__, message=str(exc))


class SnapshotBinding(JointBinding):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.adapter = SnapshotAdapter()
        self.install_error = self.restore_error = None

    def prepare(self, *args, **kwargs):
        session = super().prepare(*args, **kwargs)
        present = 'snapshot' in vars(session)
        previous = vars(session).get('snapshot')
        try:
            self.adapter.install(session)
        except BaseException as exc:
            self.install_error = describe(exc)
            # No session.start has happened. Even a partly assigned adapter must
            # not lose the prepared session's original release responsibility.
            try:
                if present:
                    session.snapshot = previous
                elif 'snapshot' in vars(session):
                    del session.snapshot
                self.adapter.restored = True
            except BaseException as undo_error:
                self.restore_error = describe(undo_error)
            try:
                session._release_owner()
            except BaseException as release_error:
                self.release_error = describe(release_error)
            raise
        return session


def finish_binding(binding, owner):
    cleanup_confirmed = (owner.get('cleanup_complete') is True
                         and (binding.cleanup or {}).get('cleanup_complete') is True)
    if cleanup_confirmed and binding.adapter.installed and not binding.adapter.restored:
        try:
            binding.adapter.restore()
        except BaseException as exc:
            binding.restore_error = describe(exc)
    return dict(prepare_calls=binding.prepare_calls, cleanup_confirmed=cleanup_confirmed,
                install_error=binding.install_error, restore_error=binding.restore_error,
                prepare_error=binding.prepare_error, release_error=binding.release_error,
                snapshot=binding.adapter.report(), snapshot_probe_started=False,
                construction_count_is_implementation_contract_not_measurement=True)


def worker(base, directory, mailbox, stop, metrics_ready):
    from heart_snapshot_guard import verify_candidate, write_new
    import joint_heart_binding as bindings
    import joint_heart_worker as inherited
    verify_candidate(Path(__file__).resolve().parent)
    directory = Path(directory)
    instances = []

    class OwnedSnapshotBinding(SnapshotBinding):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            instances.append(self)

    previous = bindings.JointBinding
    failure = None
    bindings.JointBinding = OwnedSnapshotBinding
    try:
        inherited.worker(base, directory, mailbox, stop, metrics_ready)
    except BaseException as exc:
        failure = describe(exc)
        raise
    finally:
        bindings.JointBinding = previous
        # Do not close a lease or restore an instance still used by live callers.
        # The inherited worker owns all joins, stop requests and release timing.
        post_errors = []
        owner = {}
        try:
            path = directory/'owner_result.json'
            if path.is_file():
                owner = json.loads(path.read_text(encoding='utf-8'))
        except BaseException as exc:
            post_errors.append(describe(exc))
        details = (finish_binding(instances[0], owner) if len(instances) == 1 else
                   dict(prepare_calls=0, cleanup_confirmed=False, snapshot={},
                        install_error=None, restore_error=None, prepare_error=None,
                        release_error=None, snapshot_probe_started=False))
        report = dict(schema='v3b25_heart_snapshot_owner_v1', owner_pid=os.getpid(),
                      parent_pid=os.getppid(), binding_instances=len(instances),
                      wrapper_error=failure, post_errors=post_errors, **details)
        try:
            write_new(directory/'owner_heart_snapshot.json', report)
        except BaseException as exc:
            if failure is None:
                raise
            print('附加快照报告写出失败；原错误仍保留：'+str(exc), flush=True)


def start_owner(context, base, directory, mailbox, stop, metrics_ready):
    process = context.Process(target=worker,
        args=(base, directory, mailbox, stop, metrics_ready),
        name='joint-effective25-heart-snapshot-owner', daemon=False)
    process.start()
    return process
