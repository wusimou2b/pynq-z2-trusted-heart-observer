"""No hardware: actual new live PS spawn, READY, eight receipts and exit."""
from dataclasses import replace
from functools import partial
from pathlib import Path
from zipfile import ZipFile
import json,sys


def run(root,expected,*,host=False):
    root=Path(root)
    from route_live_guard import verify
    verify(root,expected)
    from lean_ps_worker import no_hardware,load_original
    from main_ps_exit_worker import defer_offline_pandas
    with no_hardware(),defer_offline_pandas(root):
        load_original(root/'frozen')
        from compact_arm_probe import decode,encode
        with ZipFile(root/'route-probe-rows.zip') as z:
            rows=decode(json.loads(z.read('rows.json')));frames=decode(json.loads(z.read('frames.json')))
        assert len(rows)==len(frames)==8
        from route_live_runtime import installed,verified_ps
        from route_recovery import TAG
        from lean_ps_exit_trace import make_shared
        from compact_delivery_guard import BASE_SHA
        from main_rpc_compact import same_request
        import main_spatial_ps,main_heart_process
        stages=make_shared()
        class Tape:
            source='python_fixed'
            def __init__(self):self.index=0
            def reset(self):return 1
            def set_deadline(self,value):self.deadline=value
            def sample(self,r):
                row=rows[self.index];self.index+=1
                assert same_request(r,replace(row['request'],identity=r.identity))
                return replace(row['response'],identity=r.identity)
        prepared=(Path('E:/Codex-builds/main-ps-exit-green-20261027-02/lean-source0/release/v3b25-native100-heart')
                  if host else root.parent/'v3b25 native100 heart video')
        with installed(root,expected,exit_stages=stages):
            target=partial(verified_ps,root=root,expected=expected,exit_stages=stages,
                delegate=main_spatial_ps.ps_worker,manifest_sha256=BASE_SHA,source=prepared,
                host_check=host,run_id='route-live-short')
            bridge=main_heart_process.Bridge('python_fixed',target,run_id='route-live-short');tape=Tape()
            try:
                bridge.attach_backend(tape);assert bridge.reset()==1
                for row,frame in zip(rows,frames):assert encode(bridge.step(row['slot']))==encode(frame)
            finally:bridge.close()
            info=bridge.info()
            assert info['route_output_policy']==TAG and info['completed_steps']==tape.index==8
            assert info['cleanup_complete'] and info['exitcode']==0 and not info['forced_termination'],info
        assert not any(n.split('.')[0] in {'pynq','cv2','smbus'} for n in sys.modules)
        return dict(passed=True,hardware_accessed=False,points=8,actual_new_live_spawn=True,info=info)


if __name__=='__main__':
    root=Path(__file__).resolve().parent
    result=run(root,sys.argv[1],host='--host' in sys.argv[2:])
    with (root/'route-new-ps-check.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(dict(passed=True,hardware_accessed=False,points=8,natural_exit=True)))
