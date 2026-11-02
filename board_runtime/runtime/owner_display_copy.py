"""Same display protocol and lock deadlines; bulk-copy writer bytes."""
from contextlib import contextmanager
import pickle
import time

def bulk_publish(self,snapshot,*,now_ns=None):
    started=time.perf_counter_ns()
    if __package__:from . import browser_heart_transport as original
    else:import browser_heart_transport as original
    protocol=original.transport()
    new=[]
    for item in reversed(snapshot.history):
        frame=item.runtime.frame
        if frame.sequence<=self._last:break
        row=[getattr(frame,key) for key in protocol.FIELDS]
        mask=sum(1<<i for i,value in enumerate(row) if value is None)
        new.append((frame.sequence,protocol.CURVE.pack(*(0. if v is None else v for v in row),mask)))
    new.reverse()
    for index,(sequence,_) in enumerate(new):
        if sequence!=self._last+index+1:raise ValueError('history export gap; stop without recovery')
    last=new[-1][0] if new else self._last
    meta=protocol.compact(snapshot,time.monotonic_ns() if now_ns is None else now_ns)
    meta['last']=last;encoded=pickle.dumps(meta,protocol=4)
    if len(encoded)>protocol.META_BYTES:raise ValueError('bounded status capacity exceeded')
    # Create call-local writable views BEFORE acquiring the original lock.
    # No ctypes per-element assignment or decoding under it.
    ring=memoryview(self.ring).cast('B');status=memoryview(self.meta).cast('B')
    if not self.lock.acquire(timeout=.05):raise TimeoutError('display mailbox writer lock')
    try:
        for sequence,row in new:
            start=(sequence%protocol.CAPACITY)*protocol.CURVE.size
            ring[start:start+protocol.CURVE.size]=row
        status[:len(encoded)]=encoded
        self.length.value=len(encoded)
    finally:self.lock.release()
    self._last=last
    elapsed=time.perf_counter_ns()-started
    self._encoded+=len(new);self._exports+=1
    self._total_ns+=elapsed;self._max_ns=max(self._max_ns,elapsed)

@contextmanager
def bulk_owner_writer():
    if __package__:from .display_copy_transport import CopyMailbox
    else:from display_copy_transport import CopyMailbox
    owned='publish' in vars(CopyMailbox);before=CopyMailbox.publish
    CopyMailbox.publish=bulk_publish
    try:yield
    finally:
        if owned:CopyMailbox.publish=before
        else:del CopyMailbox.publish
