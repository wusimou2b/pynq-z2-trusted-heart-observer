"""Independent single-symbol GIL policy; original C and driver are untouched."""
import ctypes as C
from pathlib import Path

if __package__:from .main_heart_readback import SnapshotLibrary
else:from main_heart_readback import SnapshotLibrary

ARGUMENTS=[C.c_void_p,C.c_size_t,C.c_void_p,C.c_size_t,C.c_uint32,
           C.c_void_p,C.c_size_t,C.c_double,C.c_void_p]


class _Symbols:
    def __init__(self,original,transaction):
        self.original=original
        self.hm_transact_sample=transaction

    def __getattr__(self,name):return getattr(self.original,name)


class HeldTransactionLibrary:
    def __init__(self,original):
        if not isinstance(original,SnapshotLibrary):raise ValueError('original validated SnapshotLibrary required')
        ordinary=original.lib.hm_transact_sample
        if (ordinary.argtypes!=ARGUMENTS or ordinary.restype is not C.c_int
            or ordinary._flags_ & C._FUNCFLAG_PYTHONAPI):raise ValueError('original SAMPLE binding ABI/policy differs')
        binary=str(Path(original.lib._name).resolve(strict=True))
        bound=C.PyDLL(binary)
        transaction=bound.hm_transact_sample
        transaction.argtypes=list(ARGUMENTS);transaction.restype=C.c_int
        address=C.cast(ordinary,C.c_void_p).value
        if (not address or C.cast(transaction,C.c_void_p).value!=address
            or not transaction._flags_ & C._FUNCFLAG_PYTHONAPI):
            raise ValueError('candidate must bind SAME verified SAMPLE address with held GIL')
        self.original,self.bound_library=original,bound
        self.arm_capable=original.arm_capable
        self.lib=_Symbols(original.lib,transaction)
        self.binding_info=dict(policy='hold_gil_single_sample_v1',binary=binary,
            original_address=address,candidate_address=C.cast(transaction,C.c_void_p).value,
            only_changed_symbol='hm_transact_sample',per_call_new_clocks=0,
            original_function_flags=ordinary._flags_,candidate_function_flags=transaction._flags_)

    def check_clock(self):return self.original.check_clock()


def bind_transaction(original):return HeldTransactionLibrary(original)


def load_held(root):
    if __package__:from .main_heart_native_build import load_verified
    else:from main_heart_native_build import load_verified
    return bind_transaction(load_verified(root))
