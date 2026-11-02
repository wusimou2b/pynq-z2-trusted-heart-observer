"""Manual five-second candidate; preserve original artifacts and failure semantics."""
from functools import partial
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED

from startup_digest_guard import verify,SOURCE_SHA,MANIFEST

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def short(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    from run_fifo_time5 import short as original
    return original(expected_manifest_sha256=SOURCE_SHA)


def prepare(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    from run_fifo_time5 import prepare as original
    return original(expected_manifest_sha256=SOURCE_SHA)


def run(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-FIFO-STARTUP5':
        raise ValueError('requires RUN-FIFO-STARTUP5')
    for n in ('startup-digest5-attempt.json','startup-digest5-final.json','startup-digest5-results.zip'):
        if (ROOT/n).exists():raise FileExistsError('startup attempt exists; preserve, no retry')
    write_new(ROOT/'startup-digest5-attempt.json',dict(expected_manifest_sha256=expected_manifest_sha256,
        manual_confirmation=True,automatic_retry=False))
    checked=result=failure=None
    try:
        checked=verify(ROOT,expected_manifest_sha256)
        import run_fifo_time5 as original,fifo_time_runtime
        from status60_ab_runtime import replaced
        from startup_digest_runtime import start_owner
        with replaced(fifo_time_runtime,'start_owner',partial(start_owner,
                expected_startup_manifest_sha256=expected_manifest_sha256)):
            result=original.run(hardware=True,confirmation='RUN-FIFO-TIMING5',expected_manifest_sha256=SOURCE_SHA)
    except BaseException as exc:failure=exc
    final=dict(schema='startup_exact_bytes_five_second_result_v1',checked=checked,result=result,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        startup_timeout_seconds=180,deadline_moved=False,formal_cap_seconds=5,
        ce_policy_unchanged=True,algorithm_changed=False,hardware_changed=False,
        automatic_retry=False,live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
    try:
        write_new(ROOT/'startup-digest5-final.json',final)
        with ZipFile(ROOT/'startup-digest5-results.zip','x',compression=ZIP_DEFLATED) as z:
            for n in (MANIFEST,'startup-digest5-attempt.json','startup-digest5-final.json','fifo-time5-results.zip'):
                if (ROOT/n).is_file():z.write(ROOT/n,n)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    if failure is not None:raise failure
    print('结果：startup-digest5-results.zip；原保护保留，失败不自动重试。',flush=True)
    return final
