"""New manual gates. The retained entry and its result files stay verifiable."""
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
_IMPORT_SCOPE=None
_PREPARED=None

def check(expected):
    from lean_joint_guard import verify
    return verify(ROOT,expected)

def imports(expected):
    global _IMPORT_SCOPE
    check(expected)
    if _IMPORT_SCOPE is None:
        from main_ps_exit_worker import defer_offline_pandas
        scope=defer_offline_pandas(ROOT);scope.__enter__();_IMPORT_SCOPE=scope

def close_imports():
    global _IMPORT_SCOPE
    if _IMPORT_SCOPE is not None:
        scope=_IMPORT_SCOPE;_IMPORT_SCOPE=None;scope.__exit__(None,None,None)

def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)

def execute(stage,expected,call):
    check(expected)
    write(ROOT/('lean-'+stage+'-attempt.json'),dict(manifest_sha256=expected,automatic_retry=False))
    result=None;failure=None
    try:result=call()
    except BaseException as exc:failure=exc
    final=dict(schema='lean_joint_'+stage+'_v1',manifest_sha256=expected,result=result,
        error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)),
        live60_acceptance_passed=False,automatic_retry=False)
    write(ROOT/('lean-'+stage+'-final.json'),final)
    with ZipFile(ROOT/('lean-'+stage+'-results.zip'),'x',compression=ZIP_DEFLATED) as z:
        for name in ('lean-joint-manifest.json','lean-'+stage+'-attempt.json','lean-'+stage+'-final.json',
            'video-process20-results.zip' if stage=='preview20' else 'video-process60-results.zip',
            'video-process-short.json','lean-native-binding-check.json','continuous-results/lean-ps-exit-stages.json'):
            if (ROOT/name).is_file():z.write(ROOT/name,name)
    if failure is not None:
        close_imports();raise failure
    return final

def short(expected):
    imports(expected)
    from compact_delivery_guard import BASE_SHA
    from lean_native_binding_probe import probe
    import compact_run_video_split as original
    def run():
        binding=probe(ROOT,expected)
        write(ROOT/'lean-native-binding-check.json',binding)
        return dict(original.short(expected_manifest_sha256=BASE_SHA),native_binding_check=binding)
    return execute('short',expected,run)

def preview20(*,hardware=False,confirmation=None,expected):
    if hardware is not True or confirmation!='RUN-LEAN-VIDEO20':raise ValueError('explicit RUN-LEAN-VIDEO20 required')
    imports(expected)
    from compact_delivery_guard import BASE_SHA
    from compact_delivery_runtime import installed
    from lean_joint_guard import BASE
    import compact_run_video_split as original
    def run():
        with installed(ROOT,BASE):
            return original.qualify20(hardware=True,confirmation='RUN-VIDEO-PROCESS20',expected_manifest_sha256=BASE_SHA)
    return execute('preview20',expected,run)

def require_preview(expected):
    check(expected)
    proof=json.loads((ROOT/'lean-preview20-final.json').read_bytes())
    if proof.get('manifest_sha256')!=expected or proof.get('error') is not None or (proof.get('result') or {}).get('ownership_qualification_passed') is not True:
        raise ValueError('matching new-directory video qualification required')

def prepare(expected):
    global _PREPARED
    imports(expected);require_preview(expected)
    if _PREPARED is not None:raise RuntimeError('browser already prepared')
    from compact_delivery_guard import BASE_SHA
    import compact_run_video_split as original
    result=original.prepare_joint60(expected_manifest_sha256=BASE_SHA)
    _PREPARED=expected;return result

def joint60(*,hardware=False,confirmation=None,expected):
    if hardware is not True or confirmation!='RUN-LEAN-JOINT60':raise ValueError('explicit RUN-LEAN-JOINT60 required')
    require_preview(expected)
    if _PREPARED!=expected:raise RuntimeError('separate green browser preparation required')
    from compact_delivery_guard import BASE_SHA
    from lean_joint_runtime import installed
    import compact_run_video_split as original
    def run():
        with installed(ROOT,expected):
            return original.joint60(hardware=True,confirmation='RUN-VIDEO-PROCESS60',expected_manifest_sha256=BASE_SHA)
    try:return execute('joint60',expected,run)
    finally:close_imports()
