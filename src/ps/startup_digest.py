"""Exact-byte SHA reuse during the owner's pre-binding startup prefix only.

Every caller still reads its file and performs its existing path/policy checks.
Bytes equality, not path/mtime/size, determines a hit. Returned hash instances
are independent copies. No file contents survive the pre-binding barrier.
"""
import threading


class StartupDigests:
    def __init__(self, original, min_bytes=1024, max_bytes=32*1024*1024, max_entries=2048):
        self.original = original
        self.min_bytes, self.max_bytes, self.max_entries = min_bytes, max_bytes, max_entries
        self.thread = threading.get_ident()
        self.enabled = True
        self.values = {}
        self.entries = 0
        self.retained_bytes = self.peak_bytes = self.hits = self.computations = self.saved_input_bytes = 0

    def __call__(self, data=b'', *, usedforsecurity=True):
        if (not self.enabled or threading.get_ident() != self.thread
                or type(data) is not bytes or usedforsecurity is not True or len(data) < self.min_bytes):
            return self.original(data, usedforsecurity=usedforsecurity)
        # A bytes dict key would hash the entire freshly-read file again.
        # Length selects a bucket; exact memcmp still decides every cache hit.
        for previous, saved in self.values.get(len(data), ()):
            if data == previous:
                self.hits += 1
                self.saved_input_bytes += len(data)
                return saved.copy()
        result = self.original(data, usedforsecurity=usedforsecurity)
        self.computations += 1
        if self.entries < self.max_entries and self.retained_bytes + len(data) <= self.max_bytes:
            self.values.setdefault(len(data), []).append((data, result.copy()))
            self.entries += 1
            self.retained_bytes += len(data)
            self.peak_bytes = max(self.peak_bytes, self.retained_bytes)
        return result

    def report(self):
        return dict(hits=self.hits, computations=self.computations, saved_input_bytes=self.saved_input_bytes,
            retained_bytes=self.retained_bytes, peak_bytes=self.peak_bytes, enabled=self.enabled,
            max_bytes=self.max_bytes, max_entries=self.max_entries)

    def close(self):
        self.enabled = False
        self.values.clear()
        self.entries = 0
        self.retained_bytes = 0
