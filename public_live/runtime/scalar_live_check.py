"""Disposable preflight: keep calculation imports out of the Notebook process."""
import json
from pathlib import Path
import sys
from scalar_live_guard import verify, BASE

def binding(root,expected):
    import ctypes as C
    import gc,time
    from lean_ps_worker import no_hardware
    from main_ps_exit_worker import defer_offline_pandas
    before=gc.isenabled(),gc.get_threshold()
    with no_hardware(),defer_offline_pandas(root):
        from scalar_live_runtime import installed
        from fault_replay_native import builder
        import spatial_gil_worker as policy,main_heart_native_build as build
        old=policy.load_candidate,build.load_verified
        bindings=[]
        with installed(root,expected):
            with policy.install_policy(root,bindings):
                lib=build.load_verified(root)
                assert lib.entry_trace_report()['calls']==0 and lib.schedule_report()['calls']==0
                for _ in range(2):
                    ram,payload,result,phase=builder(root).ram_transaction_case()
                    ram[1]=0x20001;ram[3]=0x74;ram[10]=65;untouched=bytes(ram)
                    rc=lib.lib.hm_transact_sample(ram,16384,payload,22,1,C.byref(result),480,
                        time.monotonic()+.040,C.byref(phase))
                    assert rc==7 and phase.value==0 and bytes(ram)==untouched
                schedule=lib.schedule_report()
                assert schedule['calls']==2 and schedule['all_restored']
                assert lib.failure['error_code']==65
        assert old==(policy.load_candidate,build.load_verified)
    assert before==(gc.isenabled(),gc.get_threshold())
    assert not any(n.split('.')[0] in {'pynq','cv2','smbus'} for n in sys.modules)
    return dict(passed=True,hardware_accessed=False,ordinary_ram_calls=2,schedule=schedule,
        trace=lib.entry_trace_report(),receipt=lib.failure,bindings=bindings,gc_unchanged=True)

def main(mode,expected):
    root=Path(__file__).resolve().parent;verify(root,expected)
    if mode=='binding':
        result=binding(root,expected)
        with (root/'scalar-binding-check.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    elif mode=='short':
        from lean_joint_entry import short
        result=short(BASE)
    elif mode=='preview':
        from lean_joint_entry import preview20
        result=preview20(hardware=True,confirmation='RUN-LEAN-VIDEO20',expected=BASE)
    else:raise ValueError('unknown preflight mode')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':main(*sys.argv[1:])
