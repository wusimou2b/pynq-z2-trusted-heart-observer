"""Single manual AB trial; cold checks precede the retained live delegate."""
from contextlib import ExitStack
from functools import partial
import json
from pathlib import Path
import sys
import uuid
from zipfile import ZipFile,ZIP_DEFLATED

if __name__=='__main__' and not __package__:
    # Isolated (-I) CLI excludes the script directory; add only this entry's root.
    sys.path.insert(0,str(Path(__file__).resolve().parent))

if __package__:
    from .status60_ab_manifest import verify_ab_package,MANIFEST
else:
    from status60_ab_manifest import verify_ab_package,MANIFEST

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True


def write_new(path,value):
    with Path(path).open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def short(*,expected_manifest_sha256):
    verify_ab_package(ROOT,expected_manifest_sha256)
    import run_status60
    from status60_ab_runtime import replaced
    with replaced(run_status60,'ROOT',ROOT):return run_status60.short()


def prepare(*,expected_manifest_sha256):
    verify_ab_package(ROOT,expected_manifest_sha256)
    import run_status60
    from status60_ab_runtime import replaced
    with replaced(run_status60,'ROOT',ROOT):return run_status60.prepare()


def _delegate(expected_sha,epoch):
    import run_status60,status60_runtime
    from status60_ab_runtime import ab_start_owner,replaced
    with replaced(run_status60,'ROOT',ROOT),replaced(status60_runtime,'start_owner',
            partial(ab_start_owner,expected_manifest_sha256=expected_sha,run_epoch=epoch)):
        with run_status60.delegate(owner=True) as sample40:
            return sample40.run(hardware=True,confirmation='RUN-SAMPLE40-JOINT25')


def run(*,hardware=False,confirmation=None,expected_manifest_sha256):
    if hardware is not True or confirmation!='RUN-STATUS-JOINT60AB':
        raise ValueError('explicit RUN-STATUS-JOINT60AB required')
    for name in ['status60-ab-attempt.json','status60-ab-final.json','status60-ab-results.zip']:
        if (ROOT/name).exists():raise FileExistsError('AB attempt exists; preserve; no automatic retry')
    epoch=uuid.uuid4().hex
    write_new(ROOT/'status60-ab-attempt.json',dict(run_epoch=epoch,validation_pending=True,
        expected_manifest_sha256=expected_manifest_sha256,automatic_retry=False,manual_hardware_confirmation=True))
    checked=result=failure=None
    try:
        checked=verify_ab_package(ROOT,expected_manifest_sha256)
        result=_delegate(expected_manifest_sha256,epoch)
    except BaseException as exc:failure=exc
    final=dict(schema='status60_ab_result_v1',run_epoch=epoch,checked=checked,result=result,
        original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        live25_acceptance_passed=False,full_v3b_acceptance_passed=False,
        scope='A3-R/C-E concurrent60 candidate; original main PL/Native100/video/guards retained; PS exit recorded separately')
    try:
        write_new(ROOT/'status60-ab-final.json',final)
        archive=ROOT/'status60-ab-results.zip'
        with ZipFile(archive,'x',compression=ZIP_DEFLATED) as z:
            for name in [MANIFEST,'status60-ab-attempt.json','status60-ab-final.json','sample40-results.zip']:
                if (ROOT/name).is_file():z.write(ROOT/name,name)
        print('结果：status60-ab-results.zip；失败保留，不自动重试。',flush=True)
    except BaseException as export_error:
        if failure is not None:raise failure from export_error
        raise
    if failure is not None:raise failure
    return final


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--check-bundle',action='store_true',required=True)
    parser.parse_args();print(json.dumps(verify_ab_package(ROOT),ensure_ascii=False))
