"""Copy bounded shared bytes under the original lock; decode private data after."""
import math
import pickle
import time

if __package__:
    from . import browser_heart_transport as original
else:
    import browser_heart_transport as original


class CopyMailbox(original.BrowserMailbox):
    """Original writer/heartbeat/protocol/deadlines, shorter reader critical sections.

    Views are call-local, not stored on the spawned mailbox. Both ring segments
    are copied atomically under the same lock before any unpack or validation.
    This does not promise a Linux scheduling bound or suppress lock failures.
    """
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
        value = original.transport().WireSnapshot(meta, None,
            now_ns=time.monotonic_ns() if now_ns is None else now_ns, alive=alive)
        value.curve_source = self
        self._status_reads += 1
        return value

    def curve_delta(self, snapshot, after):
        protocol = original.transport()
        if after is not None and (type(after) is not int or after < -1):
            raise ValueError('invalid browser curve cursor')
        last = snapshot._last
        reset = after is None or after > last or last - after > protocol.CAPACITY
        start = max(0, last - protocol.CAPACITY + 1) if reset else after + 1
        count = last - start + 1
        row_size = protocol.CURVE.size
        index = start % protocol.CAPACITY
        first_count = min(count, protocol.CAPACITY - index)
        data = memoryview(self.ring).cast('B')
        if not 0 <= count <= protocol.CAPACITY or len(data) != protocol.CAPACITY * row_size:
            raise ValueError('invalid bounded curve copy')
        if not self.lock.acquire(timeout=.05):
            raise TimeoutError('display curve reader lock')
        try:
            first = data[index * row_size:(index + first_count) * row_size].tobytes()
            second = data[:(count - first_count) * row_size].tobytes()
        finally:
            self.lock.release()
        copied = first + second
        rows = []
        for i in range(count):
            row = protocol.CURVE.unpack_from(copied, i * row_size)
            sequence = start + i
            if row[0] != sequence:
                raise ValueError('history ring identity mismatch')
            values = [None if row[-1] & (1 << j) else row[j] for j in range(6)]
            values[0] = sequence
            if any(v is not None and not math.isfinite(v) for v in values):
                raise ValueError('nonfinite curve value')
            rows.append(values)
        self._curve_reads += 1
        self._curve_bytes += len(copied)
        self._resyncs += int(reset)
        return dict(rows=rows, reset=reset, last=last, copied_bytes=len(copied))
