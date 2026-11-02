"""Prepare an explicit new main/spatial hybrid trial, with original manual stop."""
from functools import partial
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent


def verify_package(root,expected=None):
    if __package__:from .main_spatial_guard import verify_package as verify
    else:from main_spatial_guard import verify_package as verify
    return verify(root,expected)


def short():
    if __package__:
        from . import run_lean_ps,lean_ps_worker
        from .main_spatial_ps import ps_worker
        from .joint_startup import replace_attribute
    else:
        import run_lean_ps,lean_ps_worker
        from main_spatial_ps import ps_worker
        from joint_startup import replace_attribute
    checked=verify_package(ROOT)
    with replace_attribute(lean_ps_worker,'ps_worker',ps_worker):
        report=run_lean_ps.run_short(ROOT,ROOT.parent/'v3b25 native100 heart video')
    if report['passed'] and (report.get('ready_info') or {}).get('main_heart_mode')!='one_sample_continuous_v1':
        raise RuntimeError('short result was not the new main PS target')
    # Pin the new target receipt separately from the unchanged original gate.
    path=ROOT/'main-spatial-short.json'
    with path.open('x',encoding='utf-8') as sink:
        json.dump(dict(passed=report['passed'],manifest_sha256=checked['integration_manifest_sha256'],
            target='one_sample_continuous_v1',hardware_accessed=False),sink,indent=2)
    return report


def require_short():
    checked=verify_package(ROOT)
    proof=json.loads((ROOT/'main-spatial-short.json').read_bytes())
    if not(proof.get('passed') is True and proof.get('target')=='one_sample_continuous_v1'
        and proof.get('manifest_sha256')==checked['integration_manifest_sha256'] and proof.get('hardware_accessed') is False):
        raise ValueError('new main target short exit check required')


def prepare():
    require_short()
    if __package__:
        from . import run_hybrid_display as original
        from .joint_startup import replace_attribute
    else:
        import run_hybrid_display as original
        from joint_startup import replace_attribute
    with replace_attribute(original,'ROOT',ROOT),replace_attribute(original,'verify_package',verify_package):
        return original.prepare()


def run(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-MAIN-SPATIAL25':
        raise ValueError('requires explicit RUN-MAIN-SPATIAL25')
    require_short()
    if __package__:
        from . import run_hybrid_display as original,hybrid_worker,hybrid_assessment
        from .main_spatial_worker import start_owner
        from .main_spatial_assessment import audit_artifacts
        from .joint_startup import replace_attribute
    else:
        import run_hybrid_display as original,hybrid_worker,hybrid_assessment
        from main_spatial_worker import start_owner
        from main_spatial_assessment import audit_artifacts
        from joint_startup import replace_attribute
    checked=verify_package(ROOT)
    with replace_attribute(original,'ROOT',ROOT),replace_attribute(original,'verify_package',verify_package), \
         replace_attribute(hybrid_worker,'start_owner',start_owner), \
         replace_attribute(hybrid_assessment,'audit_artifacts',audit_artifacts):
        result=original.run(hardware=True,confirmation='RUN-HYBRID25')
    verify_package(ROOT)
    archive=ROOT/'main-spatial-results.zip'
    with ZipFile(archive,'x',compression=ZIP_DEFLATED) as dest:
        with ZipFile(ROOT/'hybrid-display-results.zip') as base:
            if base.testzip() is not None or len(base.namelist())!=len(set(base.namelist())):
                raise ValueError('inherited hybrid export corrupt')
            for name in base.namelist():dest.writestr(name,base.read(name))
        for name in ('main-spatial-manifest.json','main-spatial-short.json','hardware/main-spatial-integration.json'):
            dest.write(ROOT/name,name)
    print('PL心率＋空间运动＋混合显示结果：'+str(archive),flush=True)
    from IPython.display import display,FileLink
    display(FileLink(archive.name))
    return result


if __name__=='__main__':
    import argparse
    import sys
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--check-bundle',action='store_true')
    modes.add_argument('--short',action='store_true')
    args=parser.parse_args()
    if args.check_bundle:
        print(json.dumps(verify_package(ROOT),ensure_ascii=False))
    else:
        raise SystemExit(0 if short()['passed'] else 1)
