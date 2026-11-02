"""Manual live60 entry preserving the proven original browser update policy."""
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED
from state_wire_live_guard import verify, BASE, NAME

ROOT=Path(__file__).resolve().parent
_PREPARED=None

def check(expected):return verify(ROOT,expected)

def write(path,value):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

def execute(stage,expected,call):
    check(expected)
    prefix='state-wire-'+stage
    write(ROOT/(prefix+'-attempt.json'),dict(manifest_sha256=expected,automatic_retry=False))
    result=None;failure=None
    try:result=call()
    except BaseException as exc:failure=exc
    final=dict(schema=prefix+'_v1',manifest_sha256=expected,result=result,
        error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        live60_acceptance_passed=False,automatic_retry=False)
    write(ROOT/(prefix+'-final.json'),final)
    with ZipFile(ROOT/(prefix+'-results.zip'),'x',compression=ZIP_DEFLATED) as z:
        for name in (NAME,prefix+'-attempt.json',prefix+'-final.json','state-wire-binding-check.json',
            'lean-short-results.zip','lean-preview20-results.zip','video-process60-results.zip',
            'continuous-results/transaction-schedule.json','continuous-results/lean-ps-exit-stages.json'):
            if (ROOT/name).is_file():z.write(ROOT/name,name)
    if failure is not None:raise failure
    return final

def child_check(mode,expected):
    # No timeout/terminate: preserve the original worker's exit and DMA policy.
    subprocess.run([sys.executable,'-B','-u',str(ROOT/'state_wire_live_check.py'),mode,expected],
        cwd=ROOT,check=True)

def short(expected):
    def run():
        child_check('binding',expected)
        child_check('short',expected)
        proof=json.loads((ROOT/'lean-short-final.json').read_bytes())
        if proof.get('error') is not None or not (proof.get('result') or {}).get('passed'):
            raise RuntimeError('original PS short exit incomplete')
        return dict(passed=True,hardware_accessed=False,original=proof,
            binding=json.loads((ROOT/'state-wire-binding-check.json').read_bytes()))
    return execute('short',expected,run)

def require_short(expected):
    check(expected)
    proof=json.loads((ROOT/'state-wire-short-final.json').read_bytes())
    if proof.get('manifest_sha256')!=expected or proof.get('error') is not None or (proof.get('result') or {}).get('passed') is not True:
        raise ValueError('matching scheduled short check required')

def preview20(*,hardware=False,confirmation=None,expected):
    if hardware is not True or confirmation!='RUN-STATEWIRE-VIDEO20':raise ValueError('explicit RUN-STATEWIRE-VIDEO20 required')
    require_short(expected)
    def run():
        child_check('preview',expected)
        proof=json.loads((ROOT/'lean-preview20-final.json').read_bytes())
        if proof.get('error') is not None or (proof.get('result') or {}).get('ownership_qualification_passed') is not True:
            raise RuntimeError('original video ownership/cleanup gate incomplete')
        return proof
    return execute('preview20',expected,run)

def require_preview(expected):
    require_short(expected)
    proof=json.loads((ROOT/'state-wire-preview20-final.json').read_bytes())
    if proof.get('manifest_sha256')!=expected or proof.get('error') is not None:
        raise ValueError('matching scheduled video qualification required')
    from lean_joint_entry import require_preview as retained
    retained(BASE)

def prepare(expected):
    global _PREPARED
    require_preview(expected)
    if _PREPARED is not None:raise RuntimeError('browser already prepared')
    from lean_display_bootstrap import activate_display
    activate_display(ROOT/'frozen')
    from compact_delivery_guard import BASE_SHA
    from compact_run_video_split import prepare_joint60
    result=prepare_joint60(expected_manifest_sha256=BASE_SHA)
    _PREPARED=expected
    print('正式窗口：本次全程放稳手指60秒，预热不计入。',flush=True)
    return result

def joint60(*,hardware=False,confirmation=None,expected):
    if hardware is not True or confirmation!='RUN-STATEWIRE-LIVE60':raise ValueError('explicit RUN-STATEWIRE-LIVE60 required')
    require_preview(expected)
    if _PREPARED!=expected:raise RuntimeError('separate green browser preparation required')
    from compact_delivery_guard import BASE_SHA
    from state_wire_live_runtime import parent_scope
    from compact_run_video_split import joint60 as retained
    def run():
        with parent_scope(ROOT,expected):
            return retained(hardware=True,confirmation='RUN-VIDEO-PROCESS60',expected_manifest_sha256=BASE_SHA)
    return execute('live60',expected,run)
