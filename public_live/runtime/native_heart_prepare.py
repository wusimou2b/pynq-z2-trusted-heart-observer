"""One-shot hardware-free build and strict proof, before original live startup."""
import gc
import json
from pathlib import Path
import platform
import sys
from zipfile import ZipFile,ZIP_DEFLATED

if __package__:
    from .native_heart_guard import verify_package,sha,write_new,MANIFEST,ARM_SHA
else:
    from native_heart_guard import verify_package,sha,write_new,MANIFEST,ARM_SHA


def build(*args):
    if __package__:from .statistics25_native_build import build as original
    else:from statistics25_native_build import build as original
    return original(*args)


def primitive(core):
    if __package__:from .statistics25_native_trial import primitive_proof
    else:from statistics25_native_trial import primitive_proof
    return primitive_proof(core)


def qualify(root,data,core,*,host_check,emit):
    if __package__:
        from . import statistics25_replay as replay
        from .statistics25_native import make_candidate
        from .statistics25_native_trial import _Coverage
        from .joint_startup import replace_attribute
    else:
        import statistics25_replay as replay
        from statistics25_native import make_candidate
        from statistics25_native_trial import _Coverage
        from joint_startup import replace_attribute
    counted=_Coverage(core)
    with replace_attribute(replay,'make_candidate',lambda:make_candidate(counted)):
        proof=replay.qualify(root,data,host_check=host_check,emit=emit)
    proof['native_validation_calls']=counted.counts
    return proof


def prepare(root,*,host_check=False,emit=print):
    root=Path(root).resolve()
    if any((root/n).exists() for n in ('native-build','native-prepare-attempt.json','native-prepared.json','native-prepare-results.zip')):
        raise FileExistsError('已有原生准备尝试或结果，保留，不覆盖/重试')
    checked=verify_package(root)
    arm=sys.platform=='linux' and platform.machine()=='armv7l'
    if not arm and not host_check:raise RuntimeError('原生准备只允许ARM；本机须显式host_check')
    write_new(root/'native-prepare-attempt.json',dict(automatic_retry=False,hardware_accessed=False))
    report=dict(schema='v3b25_native_heart_prepared_v1',complete=False,error=None,build=None,
        primitive=None,proof=None,configuration_unchanged=False,inputs_unchanged=False,
        performance_remeasured=False,hardware_accessed=False,host_check=host_check,arm_native=arm,
        machine=platform.machine(),native_manifest_sha256=checked['native_manifest_sha256'],
        arm_evidence_sha256=ARM_SHA,gc_before=[gc.isenabled(),list(gc.get_threshold())])
    stage='imports';numpy_before=None
    try:
        if __package__:
            from .statistics25_native import load_native,ACTIVE_METHODS
            from .statistics25_guard import read_recording
            from .ps_budget_runtime import no_hardware
        else:
            from statistics25_native import load_native,ACTIVE_METHODS
            from statistics25_guard import read_recording
            from ps_budget_runtime import no_hardware
        with no_hardware():
            import numpy as np
            numpy_before=np.geterr();report['numpy_before']=numpy_before
            emit('原生准备：不放手指、不加载电路、不采集。构建与1504点严格核对，可能数分钟。',flush=True)
            stage='build';report['build']=build(root/'statistics25_native.c',root/'native-build')
            if not report['build']['complete']:raise RuntimeError('原生构建失败，保存日志，不回退Python')
            stage='load';core=load_native(report['build']['binary'])
            report['implementation']=core.implementation
            stage='primitive';report['primitive']=primitive(core)
            if not report['primitive']['passed']:raise ValueError('primitive proof failed')
            stage='strict_proof';data=read_recording(root/'native-input.zip')
            report['proof']=qualify(root,data,core,host_check=host_check,emit=emit)
            if not report['proof']['passed'] or not all(report['proof']['native_validation_calls'][n] for n in ACTIVE_METHODS):
                raise ValueError('strict proof / active native calls failed')
            report['complete']=True
    except BaseException as exc:
        report['error']=dict(stage=stage,type=type(exc).__name__,message=str(exc))
    finally:
        report['gc_after']=[gc.isenabled(),list(gc.get_threshold())]
        if numpy_before is not None:report['numpy_after']=sys.modules['numpy'].geterr()
        report['configuration_unchanged']=(report['gc_before']==report['gc_after'] and
            numpy_before is not None and numpy_before==report.get('numpy_after'))
        try:verify_package(root);report['inputs_unchanged']=True
        except BaseException as exc:
            report['error']=report['error'] or dict(stage='post_identity',type=type(exc).__name__,message=str(exc))
        if not report['configuration_unchanged']:
            report['error']=report['error'] or dict(stage='configuration',type='RuntimeError',message='configuration changed')
        report['complete']=report['complete'] and report['error'] is None and report['inputs_unchanged']
        write_new(root/'native-prepared.json',report)
        with ZipFile(root/'native-prepare-results.zip','x',compression=ZIP_DEFLATED) as z:
            z.write(root/'native-prepared.json','native-prepared.json')
            for p in sorted((root/'native-build').glob('*')):
                if p.suffix in ('.json','.log'):z.write(p,'build/'+p.name)
    emit('原生准备完成：'+str(report['complete'])+'；错误：'+str(report['error']),flush=True)
    emit('准备结果：native-prepare-results.zip；失败不要重跑。',flush=True)
    return report


def validate_prepared(root,*,hardware):
    root=Path(root).resolve();checked=verify_package(root)
    path=root/'native-prepared.json'
    if path.is_symlink():raise ValueError('prepared report symlink')
    d=json.loads(path.read_text('utf-8'))
    if not (d.get('schema')=='v3b25_native_heart_prepared_v1' and d.get('complete') is True
            and d.get('error') is None and d.get('inputs_unchanged') is True
            and d.get('configuration_unchanged') is True and d.get('performance_remeasured') is False
            and d.get('hardware_accessed') is False and d.get('native_manifest_sha256')==checked['native_manifest_sha256']
            and d.get('arm_evidence_sha256')==ARM_SHA and d.get('implementation')=='numpy_dtype_dotfunc_100_v2'):
        raise ValueError('native preparation missing/failed/identity differs')
    p=d['proof']
    if not (d['primitive']['passed'] and p['passed'] and p['statistics_exact']
            and p['reference']['count']==p['candidate']['count']==1504
            and p['reference']['difference_count']==p['candidate']['difference_count']==0
            and p['statistics_sha256']==p['candidate_statistics_sha256']):
        raise ValueError('native preparation proof incomplete')
    if hardware and not (d['arm_native'] and not d['host_check'] and sys.platform=='linux' and platform.machine()=='armv7l'):
        raise RuntimeError('hardware requires native ARM preparation, not host-check')
    b=d['build'];binary=Path(b['binary']['path']).resolve(strict=True)
    if (not b['complete'] or b['error'] is not None or binary.parent!=root/'native-build'
            or Path(b['source']['path']).resolve()!=root/'statistics25_native.c'
            or b['source']['sha256']!=sha(root/'statistics25_native.c')
            or sha(binary)!=b['binary']['sha256']):
        raise ValueError('native build/binary identity differs')
    return dict(binary=b['binary'],implementation=d['implementation'],
        c_sha256=b['source']['sha256'],native_manifest_sha256=checked['native_manifest_sha256'],
        preparation_sha256=sha(path),host_check=d['host_check'],arm_native=d['arm_native'])
