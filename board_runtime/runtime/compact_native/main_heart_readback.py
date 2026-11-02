"""Fixed native scalar transport; original whole20ms decoder/ACK unchanged."""
import ctypes as C
import math
import sys
import time

if __package__:from .main_heart_mmio import HardwareMainChain,SampleResult,REASONS,BranchResult,BRANCHES
else:from main_heart_mmio import HardwareMainChain,SampleResult,REASONS,BranchResult,BRANCHES

ADDRESSES=tuple(range(0xa0,0xf8,4))+tuple(range(0x1000+192*8,0x1000+208*8,4))+tuple(
    a for branch in range(4) for a in range(0x1000+8*(41+32*branch),0x1000+8*(56+32*branch),4))
INDEX={address:i for i,address in enumerate(ADDRESSES)}


class DecodedBranch(C.Structure):
    _fields_=[('filtered',C.c_double),('bpm',C.c_double),('ibis',C.c_double*5),('position',C.c_double),
        ('index',C.c_uint64),('last_index',C.c_uint64),('accepted',C.c_uint64),
        ('count',C.c_uint32),('has_last',C.c_uint32),('has_bpm',C.c_uint32),('peak',C.c_uint32)]


class DecodedResult(C.Structure):
    _fields_=[('wave',C.c_double*5),('status',C.c_uint32),('candidate',C.c_int32),('output',C.c_int32),
        ('reason',C.c_uint32),('checked',C.c_uint32),('protection',C.c_uint32),('branches',DecodedBranch*4)]


class SnapshotLibrary:
    def __init__(self,library,*,require_arm=True):
        self.lib=library
        for name in ('hm_abi','hm_arm_mmio_capable'):
            fn=getattr(library,name);fn.argtypes=[];fn.restype=C.c_uint32
        library.hm_now.argtypes=[];library.hm_now.restype=C.c_double
        library.hm_read_snapshot.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_double,C.c_void_p]
        library.hm_read_snapshot.restype=C.c_int
        self.arm_capable=library.hm_arm_mmio_capable()==1
        if library.hm_abi()!=0x484d5203:raise ValueError('main snapshot C ABI differs')
        for name,want in (('hm_result_bytes',480),('hm_branch_bytes',104)):
            fn=getattr(library,name);fn.argtypes=[];fn.restype=C.c_uint32
            if fn()!=want:raise ValueError('main native C structure layout differs')
        if (C.sizeof(DecodedResult),C.sizeof(DecodedBranch))!=(480,104):raise ValueError('main Python structure layout differs')
        library.hm_decode_snapshot.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_uint32,C.c_void_p,C.c_size_t]
        library.hm_decode_snapshot.restype=C.c_int
        library.hm_transact_sample.argtypes=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_uint32,
            C.c_void_p,C.c_size_t,C.c_double,C.c_void_p]
        library.hm_transact_sample.restype=C.c_int
        if require_arm and (not self.arm_capable or hasattr(library,'hm_test_clock')):
            raise ValueError('RAM/test library cannot access physical main MMIO')

    def check_clock(self):
        before=time.monotonic();native=self.lib.hm_now();after=time.monotonic()
        if not math.isfinite(native) or not before-1e-6<=native<=after+1e-6:
            raise RuntimeError('main C/Python monotonic domains differ')
        return dict(before=before,native=native,after=after,matched=True)


class MappedSnapshot:
    def __init__(self,mmio,library):
        import numpy as np
        array=getattr(mmio,'array',None)
        if (not library.arm_capable or hasattr(library.lib,'hm_test_clock') or C.sizeof(C.c_void_p)!=4
            or sys.byteorder!='little' or (getattr(mmio,'base_addr',None),getattr(mmio,'length',None))!=(0x43ca0000,65536)
            or not mmio.device.has_capability('MEMORY_MAPPED') or type(array) is not np.ndarray
            or array.dtype!=np.dtype('uint32') or not array.dtype.isnative or array.shape!=(16384,)
            or not array.flags.c_contiguous or array.nbytes!=65536 or array.ctypes.data%4):
            raise ValueError('owned aligned original ARM main MEMORY_MAPPED window required')
        self.mmio,self.array,self.library=mmio,array,library
        self.pointer=C.c_void_p(array.ctypes.data);self.buffer=(C.c_uint32*174)();self.done=C.c_uint32()
        self.expected=(C.c_uint32*22)();self.decoded=DecodedResult()
        self.phase=C.c_uint32()

    def _copy(self,deadline):
        if type(deadline) not in (int,float) or not math.isfinite(deadline):raise ValueError('absolute main deadline required')
        self.done.value=0
        code=self.library.lib.hm_read_snapshot(self.pointer,16384,self.buffer,174,deadline,C.byref(self.done))
        if code==1:raise TimeoutError('continuous whole20ms transaction/step deadline expired; no retry')
        if code or self.done.value!=174:raise RuntimeError('native main snapshot incomplete: '+str(code))

    def snapshot(self,deadline):
        self._copy(deadline)
        return tuple(self.buffer)

    def decode(self,deadline,expected,valid):
        if (type(expected) is not list or len(expected)!=22 or type(valid) is not bool
            or any(type(v) is not int or not 0<=v<=0xffffffff for v in expected)):
            raise ValueError('bounded main native decoder identity differs')
        self.expected[:]=expected;self._copy(deadline)
        code=self.library.lib.hm_decode_snapshot(self.buffer,174,self.expected,22,int(valid),C.byref(self.decoded),480)
        if code==4:raise RuntimeError('continuous result identity/mode/payload differs')
        if code==6:raise RuntimeError('nonfinite continuous result')
        if code:raise RuntimeError('continuous original bounded result/status differs: '+str(code))
        return self.decoded

    def prepare(self,expected):
        if (type(expected) is not list or len(expected)!=22 or
            any(type(v) is not int or not 0<=v<=0xffffffff for v in expected)):
            raise ValueError('bounded main sample identity differs')
        self.expected[:]=expected

    def transact(self,deadline,valid):
        if type(valid) is not bool or not math.isfinite(deadline):raise ValueError('native main transaction controls differ')
        self.phase.value=0
        code=self.library.lib.hm_transact_sample(self.pointer,16384,self.expected,22,int(valid),
            C.byref(self.decoded),480,deadline,C.byref(self.phase))
        suffix=' phase='+str(self.phase.value)
        if code==1:raise TimeoutError('continuous whole20ms transaction/step deadline expired; no retry'+suffix)
        if code==4:raise RuntimeError('continuous native identity/mode/payload differs'+suffix)
        if code:raise RuntimeError('continuous native transaction/status invalid code='+str(code)+suffix)
        if self.phase.value!=7:raise RuntimeError('continuous native ACK incomplete'+suffix)
        return self.decoded


class NativeMain(HardwareMainChain):
    def __init__(self,mmio,reader,*,clock=time.monotonic):
        self.reader=reader;self._snapshot=();self._sampling=False
        super().__init__(mmio,clock=clock)

    def _begin(self):
        self._snapshot=();return super()._begin()

    def _poll(self):
        status=super()._poll()
        if self._sampling:
            self._time();words=self.reader.snapshot(self.active_deadline);self._time()
            if (type(words) is not tuple or len(words)!=174 or
                any(type(v) is not int or not 0<=v<=0xffffffff for v in words)):
                raise RuntimeError('native main snapshot word shape/type/range differs')
            self._snapshot=words
        return status

    def _read(self,address):
        if self._snapshot and address in INDEX:
            # Pure tuple decoding, not another device access. C checked the
            # absolute deadline before/after every physical word. The original
            # _ack still checks that SAME deadline before any ACK write and
            # after it, so a delayed decoder cannot publish/consume late data.
            # Repeating ARM clock syscalls per already-copied word added >4ms.
            return self._snapshot[INDEX[address]]
        return super()._read(address)

    def sample(self,request):
        self._sampling=True
        try:return super().sample(request)
        finally:self._sampling=False;self._snapshot=()


class NativeDecodedMain(HardwareMainChain):
    """Same protocol/ACK, native format validation, no software heart fallback."""
    def __init__(self,mmio,reader,*,clock=time.monotonic):
        self.reader=reader;super().__init__(mmio,clock=clock)

    def sample(self,request):
        if self.closed or self.fault or not self.epoch or self.mode_b is not True:
            raise RuntimeError('continuous driver closed/locked/not initialized in B: '+self.fault)
        try:
            self._validate(request);values=self._encode(request);self._begin()
            for i,v in enumerate(values):self._write(0x40+i*4,v)
            self._write(8,2);status=self._poll()
            if status&48!=48 or self._read(24)!=self.core_epoch or self._read(28)!=2:
                raise RuntimeError('continuous result identity/mode/payload differs')
            self._time();r=self.reader.decode(self.active_deadline,values,request.valid);self._time()
            if not isinstance(r,DecodedResult):raise RuntimeError('native continuous decoded structure differs')
            branches={}
            if request.valid:
                for name,b in zip(BRANCHES,r.branches):
                    branches[name]=BranchResult(b.filtered,bool(b.peak),b.bpm if b.has_bpm else None,
                        tuple(b.ibis[:b.count]),b.index,b.last_index if b.has_last else None,
                        b.position if b.has_last else None,b.accepted)
            from heart_v3a.axi_contract import NlmsReply
            reply=NlmsReply(request.identity.sequence,self.epoch,request.beta_int,r.candidate,r.output,r.status,0)
            self._ack();elapsed=self._time()-self.started
            result=SampleResult(request.identity,self.core_epoch,r.wave[0] if request.valid else None,
                r.wave[1] if request.valid else None,reply,r.wave[3] if request.valid else None,r.wave[4],
                REASONS[r.reason],bool(r.protection),bool(r.checked),branches,elapsed)
            self.previous=(request.identity,request.valid);self.next_sequence+=1;self.counts['sample']+=1;self._reply=reply
            return result
        except BaseException as exc:
            if not self.fault:self.fault=str(exc) or type(exc).__name__
            raise


class NativeTransactionMain(HardwareMainChain):
    """One C SAMPLE transaction, including original validation and ACK.

    C performs all bit/identity/finite/status validation before ACK. Only
    immutable Python receipt materialization follows; it is still included
    in the original one-second step and the ordinary ABBA end-to-end timing.
    """
    def __init__(self,mmio,reader,*,clock=time.monotonic):
        self.reader=reader;super().__init__(mmio,clock=clock)

    def sample(self,request):
        if self.closed or self.fault or not self.epoch or self.mode_b is not True:
            raise RuntimeError('continuous driver closed/locked/not initialized in B: '+self.fault)
        try:
            self._validate(request);values=self._encode(request);self.reader.prepare(values);self._begin()
            r=self.reader.transact(self.active_deadline,request.valid);elapsed=self._time()-self.started
            if not isinstance(r,DecodedResult):raise RuntimeError('native transaction decoded structure differs')
            branches={}
            if request.valid:
                for name,b in zip(BRANCHES,r.branches):
                    branches[name]=BranchResult(b.filtered,bool(b.peak),b.bpm if b.has_bpm else None,
                        tuple(b.ibis[:b.count]),b.index,b.last_index if b.has_last else None,
                        b.position if b.has_last else None,b.accepted)
            from heart_v3a.axi_contract import NlmsReply
            reply=NlmsReply(request.identity.sequence,self.epoch,request.beta_int,r.candidate,r.output,r.status,0)
            result=SampleResult(request.identity,self.core_epoch,r.wave[0] if request.valid else None,
                r.wave[1] if request.valid else None,reply,r.wave[3] if request.valid else None,r.wave[4],
                REASONS[r.reason],bool(r.protection),bool(r.checked),branches,elapsed)
            self.previous=(request.identity,request.valid);self.next_sequence+=1;self.counts['sample']+=1;self._reply=reply
            return result
        except BaseException as exc:
            if not self.fault:self.fault=str(exc) or type(exc).__name__
            raise


