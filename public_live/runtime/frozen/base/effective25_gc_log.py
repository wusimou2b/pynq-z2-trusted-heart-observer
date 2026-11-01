"""Owner-only GC observer; no per-sample work, I/O or GC policy changes."""
from array import array
import gc
import os
from threading import get_ident
from time import monotonic_ns


class GCLog:
    def __init__(self, capacity=4096):
        if not isinstance(capacity, int) or capacity <= 0:
            raise ValueError('GC记录容量必须为正整数')
        self.capacity = capacity
        self.buffer = array('q', [0]) * (capacity * 6)
        self.count = self.dropped = self.callback_errors = 0
        self.started_ns = self.finished_ns = 0
        self.before = self.after = None
        self.active = False

    def event(self, phase, info):
        # CPython GC serializes collection callbacks. No lock or growing containers.
        try:
            if self.count >= self.capacity:
                self.dropped += 1
                return
            offset = self.count * 6
            self.buffer[offset] = monotonic_ns()
            if phase not in ('start', 'stop'):
                raise ValueError('未知GC阶段')
            self.buffer[offset + 1] = 1 if phase == 'start' else 2
            self.buffer[offset + 2] = info['generation']
            self.buffer[offset + 3] = get_ident()
            self.buffer[offset + 4] = info.get('collected', 0)
            self.buffer[offset + 5] = info.get('uncollectable', 0)
            self.count += 1
        except Exception:
            # Diagnostics must not throw into hardware-owner execution.
            self.callback_errors += 1

    def start(self):
        if self.started_ns:
            raise RuntimeError('GC观察器不可重复启动')
        self.before = (gc.isenabled(), gc.get_threshold())
        self.started_ns = monotonic_ns()
        gc.callbacks.append(self.event)
        self.active = True

    def stop(self):
        if self.active:
            if self.event in gc.callbacks:
                gc.callbacks.remove(self.event)
            else:
                self.callback_errors += 1
            self.finished_ns = monotonic_ns()
            self.after = (gc.isenabled(), gc.get_threshold())
            self.active = False

    def report(self):
        unchanged = self.before is not None and self.before == self.after
        rows = []
        for index in range(self.count):
            offset = index * 6
            rows.append(dict(at_ns=self.buffer[offset],
                phase='start' if self.buffer[offset + 1] == 1 else 'stop',
                generation=self.buffer[offset + 2], tid=self.buffer[offset + 3],
                collected=self.buffer[offset + 4], uncollectable=self.buffer[offset + 5]))
        return dict(schema='effective25_owner_gc_events_v1', pid=os.getpid(),
            capacity=self.capacity, buffer_bytes=len(self.buffer) * self.buffer.itemsize,
            count=self.count, dropped=self.dropped, callback_errors=self.callback_errors,
            started_ns=self.started_ns, finished_ns=self.finished_ns,
            gc_before=self.before, gc_after=self.after, strategy_unchanged=unchanged,
            complete=bool(self.finished_ns and unchanged and not self.active
                          and not self.dropped and not self.callback_errors), events=rows)
