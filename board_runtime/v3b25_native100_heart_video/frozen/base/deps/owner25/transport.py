"""One writer, bounded shared bytes. No device or algorithm objects cross processes."""
import pickle
import struct
import time
from types import SimpleNamespace as N

CAPACITY = 500
META_BYTES = 8192
CURVE = struct.Struct('<6dB')
FIELDS = ('sequence', 'time_s', 'raw', 'mean', 'nlms_candidate', 'joint_output')
STATUS_FIELDS = FIELDS + ('output_allowed', 'bpm', 'motion', 'selected_quality',
    'contact_ready', 'selected_route', 'nlms_mix', 'reason_cn')
MAX_AGE_NS = 100_000_000


def compact(snapshot, exported_ns):
    latest = snapshot.latest
    return dict(exported_ns=exported_ns, state=snapshot.state,
        fault=None if snapshot.fault is None else snapshot.fault.reason,
        safety=dict(snapshot.counts.get('raw_safety', {})),
        latest=None if latest is None else dict(
            frame={key:getattr(latest.runtime.frame,key) for key in STATUS_FIELDS},
            read_ns=latest.saved.record.read_completed_ns, generation=latest.slot.generation))


class WireSnapshot:
    def __init__(self, meta, ring, *, now_ns, alive):
        self.state = meta['state']
        self.fault = N(reason=meta['fault']) if meta['fault'] else None
        self.counts = {'raw_safety':meta['safety']} if meta['safety'] else {}
        self.latest = None
        item = meta['latest']
        if item is not None:
            self.latest = N(runtime=N(frame=N(**item['frame'])), slot=N(generation=item['generation']),
                saved=N(record=N(read_completed_ns=item['read_ns'])))
        self._ring, self._last, self._history = ring, meta['last'], None
        self.transport_ns = meta['exported_ns']
        stale = not 0 <= now_ns-self.transport_ns <= MAX_AGE_NS
        # Empty initial preflight is harmless while the child warms up.
        if not alive or stale and self.state == 'running':
            self.state = 'faulted'
            self.fault = N(reason='显示传输过期／所有者已退出；不是当前心率')
            if self.latest is not None:
                self.latest.runtime.frame.output_allowed = False
                self.latest.runtime.frame.bpm = None

    @property
    def history(self):
        if self._history is None:
            values = []
            for sequence in range(max(0,self._last-CAPACITY+1),self._last+1):
                row = CURVE.unpack_from(self._ring,(sequence % CAPACITY)*CURVE.size)
                data = {key:None if row[-1] & (1 << i) else row[i] for i,key in enumerate(FIELDS)}
                if data['sequence'] != sequence: raise ValueError('history ring identity mismatch')
                data['sequence'] = sequence
                values.append(N(runtime=N(frame=N(**data))))
            self._history = tuple(values)
        return self._history


class Mailbox:
    def __init__(self, context):
        self.lock = context.Lock()
        self.meta = context.RawArray('B', META_BYTES)
        self.ring = context.RawArray('B', CAPACITY*CURVE.size)
        self.length = context.RawValue('I', 0)
        self.heartbeat_lock = context.Lock()
        self.heartbeat = context.RawValue('q', time.monotonic_ns())
        # Writer-local cursors are never consulted by the reader.
        self._last = -1
        self._encoded = self._exports = self._total_ns = self._max_ns = 0

    def touch(self):
        if not self.heartbeat_lock.acquire(timeout=.05): raise TimeoutError('parent heartbeat writer lock')
        try: self.heartbeat.value = time.monotonic_ns()
        finally: self.heartbeat_lock.release()

    def parent_age(self):
        if not self.heartbeat_lock.acquire(timeout=.05): raise TimeoutError('parent heartbeat reader lock')
        try: return time.monotonic_ns()-self.heartbeat.value
        finally: self.heartbeat_lock.release()

    def publish(self, snapshot, *, now_ns=None):
        started = time.perf_counter_ns()
        new = []
        for item in reversed(snapshot.history):
            frame = item.runtime.frame
            if frame.sequence <= self._last: break
            row = [getattr(frame,key) for key in FIELDS]
            mask = sum(1 << i for i,value in enumerate(row) if value is None)
            new.append((frame.sequence,CURVE.pack(*(0. if v is None else v for v in row),mask)))
        new.reverse()
        for index,(sequence,_) in enumerate(new):
            if sequence != self._last+index+1: raise ValueError('history export gap; stop without recovery')
        last = new[-1][0] if new else self._last
        meta = compact(snapshot, time.monotonic_ns() if now_ns is None else now_ns)
        meta['last'] = last
        encoded = pickle.dumps(meta, protocol=4)
        if len(encoded) > META_BYTES: raise ValueError('bounded status capacity exceeded')
        if not self.lock.acquire(timeout=.05): raise TimeoutError('display mailbox writer lock')
        try:
            for sequence,row in new:
                start = (sequence % CAPACITY)*CURVE.size
                self.ring[start:start+CURVE.size] = row
            self.meta[:len(encoded)] = encoded
            self.length.value = len(encoded)
        finally: self.lock.release()
        self._last = last
        elapsed = time.perf_counter_ns()-started
        self._encoded += len(new); self._exports += 1
        self._total_ns += elapsed; self._max_ns = max(self._max_ns,elapsed)

    def snapshot(self, *, alive=True, now_ns=None):
        if not self.lock.acquire(timeout=.05): raise TimeoutError('display mailbox reader lock')
        try:
            encoded = bytes(self.meta[:self.length.value])
            ring = bytes(self.ring)
        finally: self.lock.release()
        # All deserialization and curve construction occurs AFTER release.
        meta = pickle.loads(encoded) if encoded else dict(exported_ns=0, state='preflight',
            fault=None, safety={}, latest=None, last=-1)
        return WireSnapshot(meta, ring, now_ns=time.monotonic_ns() if now_ns is None else now_ns, alive=alive)

    def stats(self):
        return dict(exports=self._exports, encoded_frames=self._encoded,
            export_mean_ns=self._total_ns/self._exports if self._exports else None,
            export_max_ns=self._max_ns, history_capacity=CAPACITY,
            status_capacity=META_BYTES, max_status_age_ns=MAX_AGE_NS,
            export_duration_clock='perf_counter_ns',status_timestamp_clock='monotonic_ns')
