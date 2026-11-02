"""Cold identity and evidence checks for a single changed buffer-copy operation."""
import json
from pathlib import Path

if __package__:
    from .joint_video_live_guard import FLAGS,FILES as LIVE_FILES,verify_live,assess,audit_live,sha,write_new,notebook_code_hash
else:
    from joint_video_live_guard import FLAGS,FILES as LIVE_FILES,verify_live,assess,audit_live,sha,write_new,notebook_code_hash

LIVE_SHA='c1b922a58ee6506f71e60562155ae55897850cd56086452cf87c204f2ab0cd80'
METHOD='opencv_mix_channels_direct_bgr_to_existing_bgrx_preserve_zero_x_v1'
EXTRAS={'joint_video_pack.py','joint_video_pack_guard.py','run_joint_video_pack.py','README_VIDEO_PACK.md'}
FILES=LIVE_FILES|{'video-live-manifest.json'}|EXTRAS


def verify_pack(root):
    root=Path(root);checked=verify_live(root)
    if sha(root/'video-live-manifest.json')!=LIVE_SHA:raise ValueError('previous live manifest changed')
    doc=json.loads((root/'video-pack-manifest.json').read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_video_pack_package_v1' or set(doc.get('files',{}))!=FILES
            or doc.get('formal_seconds')!=20 or doc.get('target_fps')!=15 or doc.get('packing_method')!=METHOD
            or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('native packing scope/file/flags changed')
    for name,digest in doc['files'].items():
        path=root/name
        if path.is_symlink() or not path.is_file() or sha(path)!=digest:raise ValueError('packing file changed: '+name)
    if notebook_code_hash(root/'VideoPack.ipynb')!=doc.get('notebook_code_sha256'):
        raise ValueError('native packing executable Notebook changed')
    return dict(checked,packing_method=METHOD,packing_manifest_sha256=sha(root/'video-pack-manifest.json'))


def assess_pack(report):
    checks=assess(report);identity=report.get('identity') or {};p=identity.get('packing_preflight') or {}
    cases=p.get('cases') or []
    def digest(value):
        return isinstance(value,str) and len(value)==64 and all(c in '0123456789abcdef' for c in value)
    checks['native_packing_preflight']=bool(identity.get('packing_method')==METHOD and p.get('method')==METHOD
        and p.get('passed') is True and p.get('before_hardware_open') is True and p.get('ordinary_ram_only') is True
        and p.get('images_saved') is False and p.get('opencv_version')==(identity.get('camera') or {}).get('opencv_version')
        and isinstance(p.get('opencv_version'),str) and bool(p.get('opencv_version'))
        and [row.get('name') for row in cases]==['pattern','reverse','extremes']
        and all(row.get('matched') is True and row.get('direct_destination') is True and row.get('x_zero') is True
            and row.get('byte_count')==1228800 and digest(row.get('actual_sha256'))
            and row.get('actual_sha256')==row.get('expected_sha256') for row in cases))
    return checks


def audit_pack(directory,report):
    result=audit_live(directory,report);result['checks']['native_packing_rows']=False
    try:
        rows=[json.loads(line) for line in (Path(directory)/'frames.jsonl').read_text(encoding='utf-8').splitlines()]
        result['checks']['native_packing_rows']=bool(rows and all(r.get('packing_method')==METHOD for r in rows))
    except Exception as exc:
        result['error']=result['error'] or dict(type=type(exc).__name__,message=str(exc))
    return result
