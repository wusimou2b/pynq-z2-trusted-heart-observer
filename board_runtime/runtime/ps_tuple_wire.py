"""Same Pipe messages and immutable classes, positional pickle state only.

No shared-memory mailbox, batching, new messages, or global pickle mutation.
The original receiver and its identity/timeout/fault checks remain in charge.
"""
from dataclasses import fields
from functools import lru_cache
from io import BytesIO
from operator import attrgetter
from pickle import Pickler, dumps
import sys

ALLOWED = {
    'v3a_rate25.frontend.Slot', 'main_heart_mmio.SampleRequest',
    'main_heart_mmio.SampleResult', 'small_heart_model.Identity',
    'small_heart_model.BranchResult', 'heart_v3a.axi_contract.NlmsReply',
    'heart_v3a.runtime_pl_chain.PlRuntimeFrame',
    'heart_v2.runtime_main_chain.RuntimeFrame',
}


@lru_cache(maxsize=16)
def layout(cls):
    name = (cls.__module__+'.'+cls.__name__).removeprefix('v3b25_integration.board.')
    if name not in ALLOWED or not cls.__dataclass_params__.frozen:
        raise TypeError('unqualified positional wire class')
    names = tuple(f.name for f in fields(cls))
    return names, attrgetter(*names)


def restore(cls, values):
    names, _ = layout(cls)
    if type(values) is not tuple or len(values) != len(names):
        raise ValueError('positional wire field count differs')
    # Standard pickle also restores frozen dataclass state without calling init.
    result = object.__new__(cls)
    result.__dict__.update(zip(names, values))
    return result


def reduce_record(value):
    _, get = layout(type(value))
    return restore, (type(value), get(value))


class Codec:
    def __init__(self):
        self.table = None

    def dumps(self, value):
        if (type(value) is tuple and len(value)==3 and value[1] in ('error','close','reset','ready')):
            # Identity/import failures must reach the original receiver even
            # when none of the algorithm classes were allowed to load.
            return dumps(value, protocol=4)
        if self.table is None:
            table = {}
            for name in ALLOWED:
                module, cls_name = name.rsplit('.', 1)
                for prefix in ('', 'v3b25_integration.board.'):
                    loaded = sys.modules.get(prefix+module)
                    if loaded is not None:
                        cls = getattr(loaded, cls_name)
                        layout(cls)
                        table[cls] = reduce_record
            if len(table) < 8:
                raise RuntimeError('wire initialized before original algorithm classes')
            self.table = table
        stream = BytesIO()
        pickler = Pickler(stream, protocol=4)
        pickler.dispatch_table = self.table
        pickler.dump(value)
        return stream.getbuffer()


class Connection:
    def __init__(self, original):
        self.original = original
        self.codec = Codec()

    def send(self, message):
        return self.original.send_bytes(self.codec.dumps(message))

    def recv(self): return self.original.recv()
    def poll(self, timeout=0.): return self.original.poll(timeout)
    def close(self): return self.original.close()
    def __getattr__(self, name): return getattr(self.original, name)
