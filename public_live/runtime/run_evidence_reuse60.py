"""Single manual sixty-second trial, complete original lifecycle retained."""
from functools import partial
import json
from pathlib import Path
import sys
import uuid
from zipfile import ZipFile,ZIP_DEFLATED
from evidence_reuse_guard import verify,MANIFEST,AB_SHA

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True

def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

def short(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    from run_status60_ab import short as original
    import main_spatial_ps
    from status60_ab_runtime import replaced
    from evidence_reuse_runtime import verified_ps_worker
    target=partial(verified_ps_worker,expected_reuse_manifest_sha256=expected_manifest_sha256,
        expected_manifest_sha256=AB_SHA,run_epoch=uuid.uuid4().hex,run_id='main-spatial-short')
    # Spawn does not inherit this parent-only import substitution. In the fresh
    # child, the verified target calls the original unmodified spatial worker.
    with replaced(main_spatial_ps,'ps_worker',target):
        return original(expected_manifest_sha256=AB_SHA)

def prepare(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    from run_status60_ab import prepare as original
    return original(expected_manifest_sha256=AB_SHA)

def run(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-EVIDENCE-REUSE60':
        raise ValueError('requires RUN-EVIDENCE-REUSE60')
    for n in ('evidence-reuse60-attempt.json','evidence-reuse60-final.json','evidence-reuse60-results.zip'):
        if (ROOT/n).exists():raise FileExistsError('reuse60 attempt exists; keep result, no retry')
    write_new(ROOT/'evidence-reuse60-attempt.json',dict(expected_manifest_sha256=expected_manifest_sha256,
        manual_confirmation=True,automatic_retry=False))
    checked=result=failure=None
    try:
        checked=verify(ROOT,expected_manifest_sha256)
        import run_status60_ab as original,status60_ab_runtime as ab
        from evidence_reuse_runtime import start_owner
        with ab.replaced(ab,'ab_start_owner',partial(start_owner,
                expected_reuse_manifest_sha256=expected_manifest_sha256)):
            result=original.run(hardware=True,confirmation='RUN-STATUS-JOINT60AB',expected_manifest_sha256=AB_SHA)
    except BaseException as exc:failure=exc
    final=dict(schema='evidence_reuse60_result_v1',checked=checked,result=result,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        formal_seconds=60,algorithm_changed=False,hardware_changed=False,
        startup_timeout_seconds=180,ps_close_seconds=1,ce_error_limit_ns=80000000,
        automatic_retry=False,live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
    try:
        write_new(ROOT/'evidence-reuse60-final.json',final)
        with ZipFile(ROOT/'evidence-reuse60-results.zip','x',compression=ZIP_DEFLATED) as z:
            for n in (MANIFEST,'evidence-reuse60-attempt.json','evidence-reuse60-final.json','status60-ab-results.zip'):
                if (ROOT/n).is_file():z.write(ROOT/n,n)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    if failure is not None:raise failure
    print('结果 evidence-reuse60-results.zip；失败保留，不自动重试。',flush=True)
    return final
