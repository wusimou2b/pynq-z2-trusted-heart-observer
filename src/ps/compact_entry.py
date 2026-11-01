"""Manual candidate gates; retained package is independently byte-verifiable."""
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
_PREPARED=None


def check(expected):
    from compact_delivery_guard import verify
    return verify(ROOT,expected)


def write(name,data):
    with (ROOT/name).open('x',encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)


def execute(stage,expected,call):
    check(expected)
    write('compact-'+stage+'-attempt.json',dict(manifest_sha256=expected,automatic_retry=False))
    result=None;failure=None
    try:result=call()
    except BaseException as exc:failure=exc
    final=dict(schema='compact_joint25_'+stage+'_v1',manifest_sha256=expected,result=result,
        error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        sample_ipc='one_roundtrip_exact_refs_v1' if stage=='joint60' else 'not_exercised',
        raw_hz=25,processing_hz=25,video_fps=5,hardware_acceptance_passed=False,automatic_retry=False)
    write('compact-'+stage+'-final.json',final)
    with ZipFile(ROOT/('compact-'+stage+'-results.zip'),'x',compression=ZIP_DEFLATED) as z:
        for name in ('compact-delivery-manifest.json','compact-'+stage+'-attempt.json','compact-'+stage+'-final.json',
                     'video-process20-results.zip' if stage=='preview20' else 'video-process60-results.zip'):
            if (ROOT/name).is_file():z.write(ROOT/name,name)
    if failure is not None:raise failure
    return final


def short(expected):
    check(expected)
    # Retained no-hardware startup/exit gate. Compact transport has a separate
    # full saved1504 real-spawn/ARM evidence gate; do not relabel this short.
    import compact_run_video_split as original
    from compact_delivery_guard import BASE_SHA
    return execute('short',expected,lambda:original.short(expected_manifest_sha256=BASE_SHA))


def preview20(*,hardware=False,confirmation=None,expected):
    if hardware is not True or confirmation!='RUN-COMPACT-VIDEO20':raise ValueError('explicit RUN-COMPACT-VIDEO20 required')
    from compact_delivery_guard import BASE_SHA
    from compact_delivery_runtime import installed
    import compact_run_video_split as original
    def run():
        with installed(ROOT,expected):
            return original.qualify20(hardware=True,confirmation='RUN-VIDEO-PROCESS20',expected_manifest_sha256=BASE_SHA)
    return execute('preview20',expected,run)


def require_preview(expected):
    check(expected)
    proof=json.loads((ROOT/'compact-preview20-final.json').read_bytes())
    if (proof.get('manifest_sha256')!=expected or proof.get('error') is not None
            or (proof.get('result') or {}).get('ownership_qualification_passed') is not True):
        raise ValueError('matching compact video ownership/release proof required')


def prepare(expected):
    global _PREPARED
    require_preview(expected)
    if _PREPARED is not None:raise RuntimeError('already prepared; do not replace browser handshake')
    from compact_delivery_guard import BASE_SHA
    import compact_run_video_split as original
    result=original.prepare_joint60(expected_manifest_sha256=BASE_SHA)
    _PREPARED=expected
    return result


def joint60(*,hardware=False,confirmation=None,expected):
    if hardware is not True or confirmation!='RUN-COMPACT60':raise ValueError('explicit RUN-COMPACT60 required')
    require_preview(expected)
    if _PREPARED!=expected:raise RuntimeError('run separate browser preparation and wait for green first')
    from compact_delivery_guard import BASE_SHA
    from compact_delivery_runtime import installed
    import compact_run_video_split as original
    def run():
        with installed(ROOT,expected):
            return original.joint60(hardware=True,confirmation='RUN-VIDEO-PROCESS60',expected_manifest_sha256=BASE_SHA)
    return execute('joint60',expected,run)
