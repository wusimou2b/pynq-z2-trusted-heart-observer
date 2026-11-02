"""Stdlib-only identities; validate before importing algorithms or hardware."""
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import sys

MANIFEST='effective25-manifest.json'
OWNER_ENTRY_SHA='76db84f06ccb7bd943797fe02c54bd9b2879745fd532d2cada55a20b3b504629'
FLAGS=dict.fromkeys(('live_25hz_passed','live_50hz_passed','auto_beta_effect_passed',
    'board_ddr_verified','limits_frozen','run_acceptance_passed','v3a_complete'),False)
REQUIRED={'run_effective25.py','README_EFFECTIVE25.md'}|{
    'effective25/'+n+'.py' for n in ('__init__','identity','policy','frontend','safety','capture',
                                   'bridge','session','assessment','board','checks',
                                   'display','owner','display_assessment')}


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(root,name):
    if (not isinstance(name,str) or not name or '\\' in name or ':' in name
            or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts):
        raise ValueError('包内路径非法')
    path=(root/name).resolve()
    if not path.is_relative_to(root) or path==root: raise ValueError('包内路径逃逸')
    return path


def load_owner(root):
    path=Path(root)/'deps/run_v3a25_owner_display.py'
    if digest(path)!=OWNER_ENTRY_SHA: raise ValueError('冻结所有者入口身份不符')
    spec=importlib.util.spec_from_file_location('_effective25_frozen_owner',path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def validate(root):
    root=Path(root).resolve()
    document=json.loads((root/MANIFEST).read_text(encoding='utf8'))
    if (document.get('schema')!='effective25_bundle_v1'
        or (document.get('adc_hz'),document.get('raw_hz'),document.get('processing_hz'),document.get('fifo_sample_average'))!=(50,25,25,2)
        or any(document.get(k) is not False for k in FLAGS)
        or not REQUIRED<=document.get('files',{}).keys()):
        raise ValueError('有效25Hz清单范围／正式标志不符')
    tracked={str(root/MANIFEST):digest(root/MANIFEST)}
    for name,expected in document['files'].items():
        path=local(root,name)
        if not path.is_file() or digest(path)!=expected: raise ValueError('文件缺失／哈希不符：'+name)
        tracked[str(path)]=expected
    owner=load_owner(root)
    context,cached=owner.validate(root/'deps')
    context['tracked_hashes'].update(tracked)
    context['effective_root']=root
    context['effective_manifest_sha256']=tracked[str(root/MANIFEST)]
    return context,cached


def bootstrap(root,*,algorithm=False):
    context,cached=validate(root)
    root=context['effective_root']
    for name,module in tuple(sys.modules.items()):
        if name.split('.')[0]=='effective25':
            path=getattr(module,'__file__',None)
            if path and not Path(path).resolve().is_relative_to(root):
                raise ValueError('旧内核串入effective25，请使用新Notebook内核')
    if str(root) not in sys.path: sys.path.insert(0,str(root))
    if algorithm:
        cached.prepare_runtime(context)
    else:
        load_owner(root).prepare_display(context)
    return context,cached


def write_new(path,value):
    with Path(path).open('x',encoding='utf8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
