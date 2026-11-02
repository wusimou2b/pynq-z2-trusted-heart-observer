"""Apply a qualified temporary scheduling scope to the already validated symbols."""
import ctypes as C
import hashlib
import json
from pathlib import Path
import threading
import time

FIELDS=('abi stage get_error enter_error restore_error verify_error policy_before priority_before '
        'policy_after priority_after delegated primary_code return_code priority_requested reserved0 reserved1').split()
class Record(C.Structure):
    _fields_=[(name,C.c_int32) for name in FIELDS]

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(root):
    root=Path(root)
    evidence=json.loads((root/'schedule-arm-results.json').read_bytes())
    if (not evidence['complete'] or evidence['hardware_accessed'] or
            evidence['binary_sha256']!=sha(root/'libtransaction_schedule.so') or
            evidence['source_sha256']!=sha(root/'transaction_schedule.c') or
            evidence['original_policy']!=0 or evidence['original_priority']!=0 or
            evidence['peer_exitcodes']!=[0,0]):
        raise ValueError('scoped scheduling ARM qualification differs')
    held=C.PyDLL(str(root/'libtransaction_schedule.so'))
    if hasattr(held,'hs_test_reset') or hasattr(held,'hs_cpu_probe'):
        raise ValueError('production scheduling helper required')
    return held

def bind(observed,held,capacity=2048):
    if (not hasattr(observed,'_retained_gil_check') or not observed.binding_info.get(
            'original_type_abi_address_guard_retained')):
        raise ValueError('original strict identity and held GIL binding must precede scheduling')
    if getattr(observed,'_schedule_storage',None) is not None:
        raise ValueError('no scheduling rebind')
    trace,original_held,state,ordinary=observed._entry_storage
    first=original_held.hm_transact_sample_entry_trace
    if state['calls']!=0 or capacity!=2048:raise ValueError('unused bounded storage required')
    for fn in (ordinary,first):
        if not isinstance(fn,C._CFuncPtr) or not fn._flags_&C._FUNCFLAG_PYTHONAPI:
            raise ValueError('original native held GIL symbol required')
    held.hs_abi.argtypes=[];held.hs_abi.restype=C.c_uint32
    held.hs_record_bytes.argtypes=[];held.hs_record_bytes.restype=C.c_uint32
    if held.hs_abi()!=0x48534701 or held.hs_record_bytes()!=C.sizeof(Record):
        raise ValueError('scheduling ABI differs')
    targets=[];calls=[]
    for name,target in (('hs_ordinary',ordinary),('hs_traced',first)):
        fn=getattr(held,name)
        if not isinstance(fn,C._CFuncPtr) or not fn._flags_&C._FUNCFLAG_PYTHONAPI:
            raise ValueError('scheduling wrapper must retain GIL')
        fn.argtypes=[C.c_void_p]+list(target.argtypes)+[C.c_void_p,C.c_size_t];fn.restype=C.c_int
        calls.append(fn);targets.append(C.cast(target,C.c_void_p))
    records=(Record*capacity)();caller=[None]
    def call(*args):
        ident=threading.get_ident()
        if caller[0] is None:caller[0]=ident
        if ident!=caller[0]:raise RuntimeError('single transaction caller required')
        index=state['calls']
        if index>=capacity:raise RuntimeError('bounded scheduling records exhausted; no transaction')
        state['calls']+=1
        row=C.byref(records,index*C.sizeof(Record))
        if index==0:
            state['deadline_seconds']=float(args[7]);state['python_begin_ns']=time.monotonic_ns()
            try:return calls[1](targets[1],*args,C.byref(trace),240,row,64)
            finally:state['python_end_ns']=time.monotonic_ns()
        return calls[0](targets[0],*args,row,64)
    def report():
        rows=[{name:int(getattr(r,name)) for name in FIELDS} for r in records[:state['calls']]]
        return dict(calls=state['calls'],capacity=capacity,rows=rows,
                    all_restored=all(r['stage']==4 and not r['restore_error'] and not r['verify_error']
                        and r['policy_after']==0 and r['priority_after']==0 for r in rows),
                    scope='SCHED_FIFO minimum only inside original native transaction; no deadline change')
    observed.call=call;observed.schedule_report=report
    observed._schedule_storage=(held,records,caller,targets,calls)
    observed.binding_info['transaction_scoped_schedule']='SCHED_FIFO minimum, restore SCHED_OTHER before return'
    return observed

def install(observed,root):return bind(observed,load(root))
