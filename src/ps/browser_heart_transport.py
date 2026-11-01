"""Original shared writer protocol, metadata-only polls, bounded curve deltas."""
import json
import math
import pickle
import time

_BASE_MAILBOX = None
_TRANSPORT = None


def transport():
    if _TRANSPORT is not None:
        return _TRANSPORT
    from owner25 import transport as original
    return original


def base():
    return _BASE_MAILBOX if _BASE_MAILBOX is not None else transport().Mailbox


class BrowserMailbox:
    """No nested original Mailbox object: spawn keeps class identities valid."""
    def __init__(self, context):
        base().__init__(self, context)
        self._status_reads = self._curve_reads = self._curve_bytes = self._resyncs = 0

    def publish(self, *args, **kwargs):
        return base().publish(self, *args, **kwargs)

    def touch(self):
        return base().touch(self)

    def parent_age(self):
        return base().parent_age(self)

    def stats(self):
        return base().stats(self)

    def snapshot(self, *, alive=True, now_ns=None):
        if not self.lock.acquire(timeout=.05):
            raise TimeoutError('display mailbox reader lock')
        try:
            encoded = bytes(self.meta[:self.length.value])
        finally:
            self.lock.release()
        meta = pickle.loads(encoded) if encoded else dict(exported_ns=0, state='preflight',
            fault=None, safety={}, latest=None, last=-1)
        result = transport().WireSnapshot(meta, None,
            now_ns=time.monotonic_ns() if now_ns is None else now_ns, alive=alive)
        result.curve_source = self
        self._status_reads += 1
        return result

    def curve_delta(self, snapshot, after):
        protocol = transport()
        if after is not None and (type(after) is not int or after < -1):
            raise ValueError('invalid browser curve cursor')
        last = snapshot._last
        reset = after is None or after > last or last - after > protocol.CAPACITY
        start = max(0, last - protocol.CAPACITY + 1) if reset else after + 1
        rows = []
        if not self.lock.acquire(timeout=.05):
            raise TimeoutError('display curve reader lock')
        try:
            for sequence in range(start, last + 1):
                offset = sequence % protocol.CAPACITY * protocol.CURVE.size
                row = protocol.CURVE.unpack(bytes(self.ring[offset:offset + protocol.CURVE.size]))
                if row[0] != sequence:
                    raise ValueError('history ring identity mismatch')
                values = [None if row[-1] & (1 << i) else row[i] for i in range(6)]
                values[0] = sequence
                if any(v is not None and not math.isfinite(v) for v in values):
                    raise ValueError('nonfinite curve value')
                rows.append(values)
        finally:
            self.lock.release()
        copied = len(rows) * protocol.CURVE.size
        self._curve_reads += 1
        self._curve_bytes += copied
        self._resyncs += int(reset)
        return dict(rows=rows, reset=reset, last=last, copied_bytes=copied)

    def reader_stats(self):
        return dict(status_reads=self._status_reads, curve_reads=self._curve_reads,
                    curve_bytes=self._curve_bytes, resynchronizations=self._resyncs,
                    history_objects_constructed=0)
