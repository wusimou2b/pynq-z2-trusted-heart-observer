"""New observation symbol; original paired SAMPLE and Native40 guards retained."""
import ctypes as C
import importlib.util
import json
from pathlib import Path

class Receipt(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('abi','primary_code','phase','attempted','valid_mask','capture_code',
                                    'status','error_code','accepted','completed','max_compute','timer')]

def builder(root):
    path=Path(root)/'native/main_heart_native_build.py'
    spec=importlib.util.spec_from_file_location('fault_private_native_builder',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class ObservedLibrary:
    def __init__(self,original,path):
        self.original=original;self.arm_capable=original.arm_capable
        self.held=C.PyDLL(str(path));self.receipt=Receipt();self.failure=None
        size=self.held.hm_fault_receipt_bytes;size.restype=C.c_uint32;size.argtypes=[]
        if size()!=C.sizeof(Receipt) or size()!=48:raise ValueError('fault receipt ABI differs')
        self.call=self.held.hm_transact_sample_fault_receipt
        self.call.argtypes=list(original.lib.hm_transact_sample.argtypes)+[C.c_void_p,C.c_size_t]
        self.call.restype=C.c_int
        if not self.call._flags_ & C._FUNCFLAG_PYTHONAPI:raise ValueError('original held GIL required')
        outer=self
        class Symbols:
            def __getattr__(self,name):return getattr(original.lib,name)
            def hm_transact_sample(self,*args):
                code=outer.call(*args,C.byref(outer.receipt),48)
                if code and outer.failure is None:
                    outer.failure={name:int(getattr(outer.receipt,name)) for name,_ in Receipt._fields_}
                    outer.failure.update(return_code=int(code),native_phase=C.cast(args[-1],C.POINTER(C.c_uint32))[0])
                return code
        self.lib=Symbols()

    def check_clock(self):return self.original.check_clock()

def load(root,expected_build):
    from fault_replay_guard import sha
    native=Path(root)/'native'
    if sha(native/'main-native-build.json')!=expected_build:raise ValueError('ARM build report differs')
    original=builder(root).load_verified(native)
    result=ObservedLibrary(original,native/'main_native_build/libmain_heart_readback.so')
    result.check_clock();return result

def qualify(root):
    """Only ordinary allocated RAM. No device object or device mapping."""
    native=Path(root)/'native';b=builder(root);report=b.build_native(native)
    from fault_replay_guard import sha
    observed=load(root,sha(native/'main-native-build.json'))
    ram,expected,result,phase=b.ram_transaction_case()
    ram[1]=0x20001;ram[3]=0x74;ram[10]=0x41;ram[8]=1071;ram[9]=1070;ram[14]=2000000
    import time
    rc=observed.lib.hm_transact_sample(ram,16384,expected,22,1,C.byref(result),480,time.monotonic()+.040,C.byref(phase))
    f=observed.failure
    if rc!=7 or f['valid_mask']!=63 or f['error_code']!=65 or f['completed']!=1070 or ram[2]!=0:
        raise ValueError('ARM failure-only RAM receipt differs')
    return dict(build_sha256=sha(native/'main-native-build.json'),receipt=f,hardware_accessed=False,
                binary_sha256=report['binary_sha256'],abi_bytes=48,complete=True)
