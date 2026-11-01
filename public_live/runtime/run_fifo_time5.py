"""Manual actual-joint short observation; original failures/cleanup stay visible."""
from functools import partial
import json
from pathlib import Path
import sys
from zipfile import ZipFile,ZIP_DEFLATED

if __name__=='__main__' and not __package__:sys.path.insert(0,str(Path(__file__).resolve().parent))
from fifo_time_guard import verify,AB_SHA,MANIFEST

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def short(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    import run_status60_ab as original
    return original.short(expected_manifest_sha256=AB_SHA)


def prepare(*,expected_manifest_sha256):
    verify(ROOT,expected_manifest_sha256)
    import run_status60_ab as original
    return original.prepare(expected_manifest_sha256=AB_SHA)


def run(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-FIFO-TIMING5':raise ValueError('requires RUN-FIFO-TIMING5')
    if any((ROOT/n).exists() for n in ('fifo-time5-attempt.json','fifo-time5-final.json','fifo-time5-results.zip')):
        raise FileExistsError('FIFO timing already attempted; preserve, no retry')
    write_new(ROOT/'fifo-time5-attempt.json',dict(expected_manifest_sha256=expected_manifest_sha256,manual_confirmation=True,
        automatic_retry=False,scope='same current CE gate; original FIFO call observation; at most five formal seconds'))
    checked=result=failure=None
    try:
        checked=verify(ROOT,expected_manifest_sha256)
        import run_status60_ab as original,status60_ab_runtime as ab
        from fifo_time_runtime import start_owner
        with ab.replaced(ab,'ab_start_owner',partial(start_owner,expected_fifo_manifest_sha256=expected_manifest_sha256)):
            result=original.run(hardware=True,confirmation='RUN-STATUS-JOINT60AB',expected_manifest_sha256=AB_SHA)
    except BaseException as exc:failure=exc
    final=dict(schema='fifo_original_call_timing5_result_v1',checked=checked,result=result,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        formal_cap_seconds=5,ce_policy_unchanged=True,additional_iic_transactions=0,
        scope='timing diagnosis only; not evidence the new interval policy is live or60 seconds passed',
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False)
    try:
        write_new(ROOT/'fifo-time5-final.json',final)
        with ZipFile(ROOT/'fifo-time5-results.zip','x',compression=ZIP_DEFLATED) as z:
            for n in (MANIFEST,'fifo-time5-attempt.json','fifo-time5-final.json','status60-ab-results.zip'):
                if (ROOT/n).is_file():z.write(ROOT/n,n)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    print('结果 fifo-time5-results.zip；当前C-E可提前停止，保留结果，不自动重试。',flush=True)
    if failure is not None:raise failure
    return final


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--check-bundle',action='store_true',required=True);p.parse_args()
    print(json.dumps(verify(ROOT),ensure_ascii=False))
