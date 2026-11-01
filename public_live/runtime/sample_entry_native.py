"""Preallocated first SAMPLE trace; later calls use the retained receipt symbol."""
import ctypes as C
import hashlib,json,time
from pathlib import Path


class SampleTrace(C.Structure):
    _fields_=[(n,C.c_uint32) for n in ('abi','mask','clock_error','primary_code','phase_end','reserved0','reserved1','reserved2')]+[
        ('wall_ns',C.c_uint64*13),('cpu_ns',C.c_uint64*13)]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind_first(observed,held):
    size=held.hm_sample_trace_bytes;size.argtypes=[];size.restype=C.c_uint32
    if size()!=240 or C.sizeof(SampleTrace)!=240:raise ValueError('SAMPLE trace ABI differs')
    fn=held.hm_transact_sample_entry_trace
    fn.argtypes=list(observed.call.argtypes)+[C.c_void_p,C.c_size_t];fn.restype=C.c_int
    trace=SampleTrace();old=observed.call
    state=dict(calls=0,python_begin_ns=None,python_end_ns=None,deadline_seconds=None)
    def call(*args):
        state['calls']+=1
        if state['calls']!=1:return old(*args)
        state['deadline_seconds']=float(args[7]);state['python_begin_ns']=time.monotonic_ns()
        try:return fn(*args,C.byref(trace),240)
        finally:state['python_end_ns']=time.monotonic_ns()
    def report():
        value={name:int(getattr(trace,name)) for name,_ in SampleTrace._fields_[:8]}
        return dict(state,trace=value,wall_ns=list(trace.wall_ns),cpu_ns=list(trace.cpu_ns),
            traced_calls=min(state['calls'],1),ordinary_calls=max(state['calls']-1,0),
            scope='first actual SAMPLE only; later calls original receipt; clocks add observation overhead')
    observed.call=call;observed.entry_trace_report=report
    # Keep both preallocated storage and the library alive until all callers stop.
    observed._entry_storage=(trace,held,state,old)
    return observed


def load(root,expected_build,*,release_contract=None):
    from fault_replay_native import load as retained_load
    root=Path(root)
    if release_contract is not None:
        from public_live_contract import verified_asset
        verified_asset(release_contract,'sample_entry_binary',root/'sample-entry.so')
    q=json.loads((root/'sample-entry-qualification.json').read_bytes())
    if (not q['complete'] or q['hardware_accessed'] or q['binary_sha256']!=sha(root/'sample-entry.so')
            or q['source_sha256']!=sha(root/'sample-entry.c')):
        raise ValueError('SAMPLE trace qualification differs')
    held=C.PyDLL(str(root/'sample-entry.so'))
    held.hm_arm_mmio_capable.argtypes=[];held.hm_arm_mmio_capable.restype=C.c_uint32
    if held.hm_arm_mmio_capable()!=1 or hasattr(held,'hm_test_clock'):
        raise ValueError('physical ARM trace required')
    original=(retained_load(root,expected_build) if release_contract is None else
              retained_load(root,expected_build,release_contract=release_contract))
    result=bind_first(original,held)
    if not held.hm_transact_sample_entry_trace._flags_ & C._FUNCFLAG_PYTHONAPI:
        raise ValueError('original held GIL required')
    return result
