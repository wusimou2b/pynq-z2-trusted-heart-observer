"""Fixed message packing, same frozen records and original Pipe ownership.

Only the private serialization changes. No global pickle hooks, batching,
shared mutable records, dropped fields or bypass of the original receiver.
"""
from dataclasses import fields
from operator import attrgetter
from pickle import dumps, loads
import sys

TAG = 'v3b25_same_records_flat_v1'
CLASSES = (
    'v3a_rate25.frontend.Slot', 'main_heart_mmio.SampleRequest',
    'main_heart_mmio.SampleResult', 'small_heart_model.Identity',
    'small_heart_model.BranchResult', 'heart_v3a.axi_contract.NlmsReply',
    'heart_v3a.runtime_pl_chain.PlRuntimeFrame',
    'heart_v2.runtime_main_chain.RuntimeFrame',
)


class Record:
    def __init__(self, cls):
        if not cls.__dataclass_params__.frozen:
            raise TypeError('original immutable wire record required')
        self.cls = cls
        self.names = tuple(f.name for f in fields(cls))
        self.get = attrgetter(*self.names)

    def pack(self, value):
        if type(value) is not self.cls:
            raise TypeError('original wire record type differs')
        return self.get(value)

    def unpack(self, value):
        if type(value) is not tuple or len(value) != len(self.names):
            raise ValueError('wire record field count/type differs')
        obj = object.__new__(self.cls)
        obj.__dict__.update(zip(self.names, value))
        return obj


class Codec:
    def __init__(self):
        self.ready = False

    def initialize(self):
        records = []
        for full in CLASSES:
            module, name = full.rsplit('.', 1)
            found = [sys.modules[p+module] for p in ('', 'v3b25_integration.board.')
                     if p+module in sys.modules]
            if len(found) != 1:
                raise RuntimeError('wire original class missing or ambiguous: '+full)
            records.append(Record(getattr(found[0], name)))
        (self.slot, self.request, self.sample, self.identity, self.branch,
         self.reply, self.pl_frame, self.frame) = records
        self.req_identity = self.request.names.index('identity')
        self.sample_identity = self.sample.names.index('identity')
        self.sample_reply = self.sample.names.index('reply')
        self.sample_branches = self.sample.names.index('branches')
        self.pl_inner = self.pl_frame.names.index('frame')
        self.ready = True

    def pack(self, message):
        if type(message) is not tuple or len(message) != 3:
            raise ValueError('original message shape differs')
        rid, kind, value = message
        if kind not in ('step', 'done') or kind == 'done' and type(value) is int:
            # READY/errors/close/reset need no algorithm imports, like before.
            return message
        if not self.ready:
            self.initialize()
        if kind == 'step':
            if type(value) is not tuple or len(value) != 4:
                raise ValueError('original four-part step required')
            slot, controls, request, sample = value
            request = list(self.request.pack(request))
            request[self.req_identity] = self.identity.pack(request[self.req_identity])
            sample = list(self.sample.pack(sample))
            sample[self.sample_identity] = self.identity.pack(sample[self.sample_identity])
            if sample[self.sample_reply] is not None:
                sample[self.sample_reply] = self.reply.pack(sample[self.sample_reply])
            branches = sample[self.sample_branches]
            if type(branches) is not dict:
                raise TypeError('original branches mapping required')
            sample[self.sample_branches] = tuple((name, self.branch.pack(item))
                                                for name, item in branches.items())
            payload = (self.slot.pack(slot), controls, tuple(request), tuple(sample))
        else:
            frame = list(self.pl_frame.pack(value))
            frame[self.pl_inner] = self.frame.pack(frame[self.pl_inner])
            payload = tuple(frame)
        return TAG, rid, kind, payload

    def unpack(self, message):
        if type(message) is not tuple:
            raise ValueError('wire message type differs')
        if len(message) == 3:
            if message[1] == 'step' or message[1] == 'done' and type(message[2]) is not int:
                raise ValueError('mixed original/candidate wire')
            return message
        if len(message) != 4 or message[0] != TAG or message[2] not in ('step', 'done'):
            raise ValueError('wire version/shape differs')
        if not self.ready:
            self.initialize()
        _, rid, kind, value = message
        if kind == 'step':
            if type(value) is not tuple or len(value) != 4:
                raise ValueError('wire step shape differs')
            slot, controls, request, sample = value
            # Validate full lengths before indexing nested fields.
            request = self.request.unpack(request)
            sample = self.sample.unpack(sample)
            object.__setattr__(request, 'identity', self.identity.unpack(request.identity))
            object.__setattr__(sample, 'identity', self.identity.unpack(sample.identity))
            if sample.reply is not None:
                object.__setattr__(sample, 'reply', self.reply.unpack(sample.reply))
            if type(sample.branches) is not tuple:
                raise ValueError('wire branch sequence differs')
            branches = {}
            for pair in sample.branches:
                if type(pair) is not tuple or len(pair) != 2 or pair[0] in branches:
                    raise ValueError('wire duplicate/malformed branch')
                branches[pair[0]] = self.branch.unpack(pair[1])
            object.__setattr__(sample, 'branches', branches)
            payload = self.slot.unpack(slot), controls, request, sample
        else:
            payload = self.pl_frame.unpack(value)
            object.__setattr__(payload, 'frame', self.frame.unpack(payload.frame))
        return rid, kind, payload

    def dumps(self, message):
        return dumps(self.pack(message), protocol=4)

    def loads(self, data):
        return self.unpack(loads(data))


class Connection:
    def __init__(self, original):
        self.original, self.codec = original, Codec()

    def send(self, message):
        return self.original.send_bytes(self.codec.dumps(message))

    def recv(self):
        return self.codec.loads(self.original.recv_bytes())

    def poll(self, timeout=0.): return self.original.poll(timeout)
    def close(self): return self.original.close()
    def __getattr__(self, name): return getattr(self.original, name)
