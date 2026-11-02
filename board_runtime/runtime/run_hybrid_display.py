"""Manual mixed display entry using the original browser and stop path."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

if __package__:
    from .hybrid_guard import verify_package,MANIFEST
else:
    from hybrid_guard import verify_package,MANIFEST

ROOT=Path(__file__).resolve().parent


def prepare():
    verify_package(ROOT)
    if __package__:
        from . import run_video_motion as original
        from .joint_startup import replace_attribute
    else:
        import run_video_motion as original
        from joint_startup import replace_attribute
    with replace_attribute(original,'ROOT',ROOT),replace_attribute(original,'verify_package',verify_package):
        return original.prepare()


def run(*,hardware=False,confirmation=None):
    if hardware is not True or confirmation!='RUN-HYBRID25':raise ValueError('requires RUN-HYBRID25')
    if __package__:
        from . import run_video_motion as original,video_motion_worker,shadow_assessment
        from .hybrid_worker import start_owner
        from .hybrid_assessment import audit_artifacts
        from .joint_startup import replace_attribute
    else:
        import run_video_motion as original,video_motion_worker,shadow_assessment
        from hybrid_worker import start_owner
        from hybrid_assessment import audit_artifacts
        from joint_startup import replace_attribute
    checked=verify_package(ROOT)
    with replace_attribute(original,'ROOT',ROOT),replace_attribute(original,'verify_package',verify_package), \
         replace_attribute(video_motion_worker,'start_owner',start_owner), \
         replace_attribute(shadow_assessment,'audit_shadow_artifacts',audit_artifacts):
        result=original.run(hardware=True,confirmation='RUN-FULL-MOTION25')
    verify_package(ROOT,checked['manifest_sha256'])
    archive=ROOT/'hybrid-display-results.zip'
    with ZipFile(archive,'x',compression=ZIP_DEFLATED) as dest:
        with ZipFile(ROOT/'baseline-motion-results.zip') as source:
            if source.testzip() is not None or len(source.namelist())!=len(set(source.namelist())):
                raise ValueError('base results corrupt')
            for name in source.namelist():dest.writestr(name,source.read(name))
        dest.write(ROOT/MANIFEST,MANIFEST)
    print('混合显示结果：'+archive.name+'；请回传。',flush=True)
    from IPython.display import display,FileLink
    display(FileLink(archive.name))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check-bundle',action='store_true',required=True);p.parse_args()
    print(json.dumps(verify_package(ROOT),ensure_ascii=False))
