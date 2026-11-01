"""Preserved four-stage live60 entry, with only parent metadata recheck added."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from handoff_live_guard import verify, BASE, NAME

ROOT = Path(__file__).resolve().parent
_PREPARED = None


def check(expected): return verify(expected, ROOT)


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def execute(stage, expected, call, *, handoff=None):
    check(expected)
    prefix = 'handoff-'+stage
    write(ROOT/(prefix+'-attempt.json'), dict(manifest_sha256=expected, automatic_retry=False))
    result = failure = None
    try: result = call()
    except BaseException as exc: failure = exc
    final = dict(schema=prefix+'_v1', manifest_sha256=expected, result=result, handoff=handoff,
        error=None if failure is None else dict(type=type(failure).__name__, message=str(failure)),
        live60_acceptance_passed=False, automatic_retry=False)
    write(ROOT/(prefix+'-final.json'), final)
    with ZipFile(ROOT/(prefix+'-results.zip'), 'x', compression=ZIP_DEFLATED) as archive:
        for name in (NAME, prefix+'-attempt.json', prefix+'-final.json', 'route-'+stage+'-results.zip'):
            if (ROOT/name).is_file(): archive.write(ROOT/name, name)
    if failure is not None: raise failure
    return final


def short(expected):
    def call():
        from route_live_entry import short as retained
        return retained(BASE)
    return execute('short', expected, call)


def require_stage(stage, expected):
    check(expected)
    result = json.loads((ROOT/('handoff-'+stage+'-final.json')).read_bytes())
    original = result.get('result') or {}
    if (result.get('manifest_sha256') != expected or result.get('error') is not None
        or original.get('error') is not None or not original):
        raise ValueError('matching handoff '+stage+' required')
    if stage == 'short' and (original.get('result') or {}).get('passed') is not True:
        raise ValueError('matching passed handoff short required')


def preview20(*, hardware=False, confirmation=None, expected):
    if hardware is not True or confirmation != 'RUN-HANDOFF-VIDEO20':
        raise ValueError('explicit RUN-HANDOFF-VIDEO20 required')
    require_stage('short', expected)
    def call():
        from route_live_entry import preview20 as retained
        return retained(hardware=True, confirmation='RUN-ROUTE-VIDEO20', expected=BASE)
    return execute('preview20', expected, call)


def prepare(expected):
    global _PREPARED
    require_stage('short', expected); require_stage('preview20', expected)
    if _PREPARED is not None: raise RuntimeError('browser already prepared')
    from route_live_entry import prepare as retained
    result = retained(BASE)
    _PREPARED = expected
    return result


def joint60(*, hardware=False, confirmation=None, expected):
    if hardware is not True or confirmation != 'RUN-HANDOFF-LIVE60':
        raise ValueError('explicit RUN-HANDOFF-LIVE60 required')
    require_stage('short', expected); require_stage('preview20', expected)
    if _PREPARED != expected: raise RuntimeError('separate browser preparation required')
    handoff = {}
    def call():
        from route_live_entry import joint60 as retained
        from display_status_handoff import installed
        try:
            with installed() as audit:
                return retained(hardware=True, confirmation='RUN-ROUTE-LIVE60', expected=BASE)
        finally:
            if 'audit' in locals(): handoff.update(audit)
    return execute('live60', expected, call, handoff=handoff)
