"""One60s joint candidate; retained release and all protection budgets unchanged."""
from functools import partial
import json
from pathlib import Path
import sys
import zipfile
from owner_schedule_guard import verify,SOURCE_SHA,MANIFEST

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True

def write(path,value):
    with path.open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)

def short(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    import run_evidence_reuse60 as original,evidence_reuse_runtime as runtime
    from owner_schedule_runtime import replaced,verified_ps_worker
    with replaced(runtime,'verified_ps_worker',partial(verified_ps_worker,expected_schedule_manifest_sha256=expected_manifest_sha256)):
        return original.short(expected_manifest_sha256=SOURCE_SHA)

def prepare(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    from run_evidence_reuse60 import prepare as original
    return original(expected_manifest_sha256=SOURCE_SHA)

def run(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-OWNER-DISPLAY60':raise ValueError('explicit RUN-OWNER-DISPLAY60 required')
    if any((ROOT/n).exists() for n in ('owner-display-attempt.json','owner-display-final.json','owner-display-results.zip','evidence-reuse60-attempt.json')):
        raise FileExistsError('existing joint attempt; preserve result, no retry')
    checked=verify(ROOT,expected_manifest_sha256)
    write(ROOT/'owner-display-attempt.json',dict(manifest_sha256=expected_manifest_sha256,automatic_retry=False,hardware_requested=True))
    result=failure=None
    try:
        import run_evidence_reuse60 as original,evidence_reuse_runtime as runtime
        from owner_schedule_runtime import replaced,start_owner
        with replaced(runtime,'start_owner',partial(start_owner,expected_schedule_manifest_sha256=expected_manifest_sha256)):
            result=original.run(hardware=True,confirmation='RUN-EVIDENCE-REUSE60',expected_manifest_sha256=SOURCE_SHA)
    except BaseException as exc:failure=exc
    final=dict(schema='owner_display60_result_v1',checked=checked,result=result,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False,automatic_retry=False)
    write(ROOT/'owner-display-final.json',final)
    with zipfile.ZipFile(ROOT/'owner-display-results.zip','x',compression=zipfile.ZIP_DEFLATED) as z:
        for name in (MANIFEST,'owner-display-attempt.json','owner-display-final.json','evidence-reuse60-results.zip'):
            if (ROOT/name).is_file():z.write(ROOT/name,name)
    if failure is not None:raise failure
    return final
