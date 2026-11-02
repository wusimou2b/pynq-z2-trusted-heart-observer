"""One manual60s trial after file/timing validation and original no-hardware gate."""
from functools import partial
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED

if __package__:
    from .journal60_guard import verify,SOURCE_SHA,MANIFEST
    from .journal60_runtime import replaced
else:
    from journal60_guard import verify,SOURCE_SHA,MANIFEST
    from journal60_runtime import replaced

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True

def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

def short(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    import run_owner_schedule60 as original,owner_schedule_runtime as runtime
    if __package__:from .journal60_runtime import verified_ps_worker
    else:from journal60_runtime import verified_ps_worker
    with replaced(runtime,'verified_ps_worker',partial(verified_ps_worker,
            expected_journal_manifest_sha256=expected_manifest_sha256)):
        return original.short(expected_manifest_sha256=SOURCE_SHA)

def prepare(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    from run_owner_schedule60 import prepare as original
    return original(expected_manifest_sha256=SOURCE_SHA)

def run(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-JOURNAL60':raise ValueError('explicit RUN-JOURNAL60 required')
    if any((ROOT/n).exists() for n in ('journal60-attempt.json','journal60-final.json','journal60-results.zip','owner-display-attempt.json')):
        raise FileExistsError('existing handoff attempt; preserve results, no retry')
    checked=verify(ROOT,expected_manifest_sha256)
    write(ROOT/'journal60-attempt.json',dict(manifest_sha256=expected_manifest_sha256,manual_confirmation=True,automatic_retry=False))
    result=failure=None
    try:
        import run_owner_schedule60 as original,owner_schedule_runtime as runtime,continuous_run as parent
        if __package__:from .journal60_runtime import start_owner
        else:from journal60_runtime import start_owner
        with replaced(runtime,'start_owner',partial(start_owner,expected_journal_manifest_sha256=expected_manifest_sha256)):
            result=original.run(hardware=True,confirmation='RUN-OWNER-DISPLAY60',expected_manifest_sha256=SOURCE_SHA)
    except BaseException as exc:failure=exc
    final=dict(schema='journal60_result_v1',checked=checked,result=result,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        native40_python_step1=True,protection_scope_changed=True,ipc_protocol_changed=False,scalar_journal_conversion=True,automatic_retry=False,
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
    write(ROOT/'journal60-final.json',final)
    with ZipFile(ROOT/'journal60-results.zip','x',compression=ZIP_DEFLATED) as z:
        for name in (MANIFEST,'journal60-arm-evidence.json','journal60-scalar-evidence.json','journal60-attempt.json','journal60-final.json','owner-display-results.zip'):
            if (ROOT/name).is_file():z.write(ROOT/name,name)
    if failure is not None:raise failure
    return final
