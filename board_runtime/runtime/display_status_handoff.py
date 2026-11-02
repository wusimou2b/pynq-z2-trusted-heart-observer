"""Recheck an obsolete private copy once, without waiting for a new publish.

No timestamp is renewed. Every returned status still passes the original
WireSnapshot age/death check; sample age remains the original source age.
Healthy polls use exactly the original one copy, decode and clock reading.
"""
from contextlib import contextmanager
import pickle
import time

if __package__:
    from . import display_copy_transport as retained
else:
    import display_copy_transport as retained


def _recheck(box, previous, protocol, *, alive, now_ns):
    box._handoff_checks = getattr(box, '_handoff_checks', 0) + 1
    if not box.lock.acquire(False):
        box._handoff_busy = getattr(box, '_handoff_busy', 0) + 1
        return None
    try:
        data = memoryview(box.meta).cast('B')
        size = box.length.value
        if not 0 <= size <= len(data):
            raise ValueError('invalid display status length')
        encoded = data[:size].tobytes()
    finally:
        box.lock.release()
    # Decode only the copied bytes. The writer never waits for our decoder.
    current = pickle.loads(encoded) if encoded else previous
    if current['exported_ns'] <= previous['exported_ns']:
        return None
    checked_ns = time.monotonic_ns() if now_ns is None else now_ns
    result = protocol.WireSnapshot(current, None, now_ns=checked_ns, alive=alive)
    box._handoff_last = (previous['exported_ns'], current['exported_ns'], checked_ns)
    if result.fault is None:
        box._handoff_recovered = getattr(box, '_handoff_recovered', 0) + 1
    return result


def snapshot(self, *, alive=True, now_ns=None):
    data = memoryview(self.meta).cast('B')
    if not self.lock.acquire(timeout=.05):
        raise TimeoutError('display mailbox reader lock')
    try:
        size = self.length.value
        if not 0 <= size <= len(data):
            raise ValueError('invalid display status length')
        encoded = data[:size].tobytes()
    finally:
        self.lock.release()
    meta = pickle.loads(encoded) if encoded else dict(exported_ns=0, state='preflight',
        fault=None, safety={}, latest=None, last=-1)
    protocol = retained.original.transport()
    checked_ns = time.monotonic_ns() if now_ns is None else now_ns
    value = protocol.WireSnapshot(meta, None, now_ns=checked_ns, alive=alive)
    # The common path adds only this branch. A real fault, dead owner or a
    # future timestamp is never replaced by a more convenient later status.
    if (value.fault is not None and alive and meta['state'] == 'running'
            and not meta['fault'] and not meta['safety'].get('fault')
            and checked_ns - meta['exported_ns'] > protocol.MAX_AGE_NS):
        current = _recheck(self, meta, protocol, alive=alive, now_ns=now_ns)
        if current is not None:
            value = current
    value.curve_source = self
    self._status_reads += 1
    return value


def audit(box):
    """Cold summary only; no per-poll timing, journal, IPC or growing buffer."""
    return dict(rechecks=getattr(box, '_handoff_checks', 0),
        recovered=getattr(box, '_handoff_recovered', 0),
        writer_busy=getattr(box, '_handoff_busy', 0),
        last_timestamps=getattr(box, '_handoff_last', None),
        maximum_reads_per_poll=2, recheck_wait_seconds=0,
        original_age_limit_ns=retained.original.transport().MAX_AGE_NS)


@contextmanager
def installed():
    """Notebook parent only. Existing owner/video process classes stay intact."""
    cls = retained.CopyMailbox
    original_init, original_snapshot = cls.__init__, cls.snapshot
    if original_snapshot is snapshot:
        raise RuntimeError('display handoff scope already installed')
    boxes = []
    report = {}

    def initialize(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        boxes.append(self)

    owned_init = '__init__' in vars(cls)
    cls.__init__, cls.snapshot = initialize, snapshot
    try:
        yield report
    finally:
        cls.snapshot = original_snapshot
        if owned_init:
            cls.__init__ = original_init
        else:
            del cls.__init__
        report['readers'] = [audit(box) for box in boxes]
        report['restored'] = True
        boxes.clear()
