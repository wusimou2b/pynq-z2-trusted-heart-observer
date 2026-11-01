"""New one-attempt manual demo; preserved handoff entry owns all prerequisites."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from demo_continuous_guard import verify, BASE, NAME

ROOT = Path(__file__).resolve().parent
_PREPARED = None


def check(expected): return verify(expected, ROOT)


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


def execute(stage, expected, call):
    check(expected)
    prefix = 'demo-'+stage
    write(ROOT/(prefix+'-attempt.json'), dict(manifest_sha256=expected, automatic_retry=False))
    result = failure = None
    try: result = call()
    except BaseException as exc: failure = exc
    final = dict(schema=prefix+'_v1', manifest_sha256=expected, result=result,
        error=None if failure is None else dict(type=type(failure).__name__, message=str(failure)),
        duration_mode='manual_until_stop_v1', continuous_live_passed=False, automatic_retry=False)
    write(ROOT/(prefix+'-final.json'), final)
    old_stage = 'live60' if stage == 'continuous' else stage
    with ZipFile(ROOT/(prefix+'-results.zip'), 'x', compression=ZIP_DEFLATED) as archive:
        for name in (NAME, prefix+'-attempt.json', prefix+'-final.json',
            'handoff-'+old_stage+'-results.zip', 'continuous-results/demo-continuous-owner.json'):
            if (ROOT/name).is_file(): archive.write(ROOT/name, name)
    if failure is not None: raise failure
    return final


def short(expected):
    def call():
        from handoff_live_entry import short as retained
        return retained(BASE)
    return execute('short', expected, call)


def require_stage(stage, expected):
    check(expected)
    report = json.loads((ROOT/('demo-'+stage+'-final.json')).read_bytes())
    if report.get('manifest_sha256') != expected or report.get('error') is not None:
        raise ValueError('matching continuous demo '+stage+' required')
    from handoff_live_entry import require_stage as retained
    retained(stage, BASE)


def preview20(*, hardware=False, confirmation=None, expected):
    if hardware is not True or confirmation != 'RUN-DEMO-VIDEO20':
        raise ValueError('explicit RUN-DEMO-VIDEO20 required')
    require_stage('short', expected)
    def call():
        from handoff_live_entry import preview20 as retained
        return retained(hardware=True, confirmation='RUN-HANDOFF-VIDEO20', expected=BASE)
    return execute('preview20', expected, call)


def prepare(expected):
    global _PREPARED
    require_stage('short', expected); require_stage('preview20', expected)
    if _PREPARED is not None: raise RuntimeError('browser already prepared')
    from handoff_live_entry import prepare as retained
    result = retained(BASE)
    _PREPARED = expected
    print('持续演示已准备：第四单元启动；在本单元的“正常停止并导出”按钮停止。不会60秒自动结束。', flush=True)
    return result


def run(*, hardware=False, confirmation=None, expected):
    if hardware is not True or confirmation != 'RUN-DEMO-CONTINUOUS25':
        raise ValueError('explicit RUN-DEMO-CONTINUOUS25 required')
    require_stage('short', expected); require_stage('preview20', expected)
    if _PREPARED != expected: raise RuntimeError('separate browser preparation required')
    def call():
        from demo_continuous_runtime import parent_scope
        from handoff_live_entry import joint60 as retained
        # Historical nested names remain audit provenance, not duration control.
        with parent_scope(ROOT, expected):
            return retained(hardware=True, confirmation='RUN-HANDOFF-LIVE60', expected=BASE)
    return execute('continuous', expected, call)
