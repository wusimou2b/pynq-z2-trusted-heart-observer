"""Display closure and predecessor evidence, separate from editable Notebooks."""
import importlib
import json
from pathlib import Path
import sys
from pilot25.delivery import FLAGS, digest, local, new_output, validate as validate_static

STATIC_ZIP_SHA = '802426cec5a5ee6a4204e50170c1ba372d88fd38e813022e4526e465019d5ba3'
STATIC_MANIFEST_SHA = '0130ee3c7ff1f36951bf69ce88c1374659d71f3256348f84d8bf7ea917b9183f'
REQUIRED = {'run_v3a25_display.py','README_DISPLAY25.md','static/pilot25-manifest.json','evidence/static-capture-audit.json'}
REQUIRED |= {'display25/'+name+'.py' for name in ('__init__','delivery','render','assessment','runner')}


def validate(root):
    root = Path(root).resolve()
    doc = json.loads((root/'display25-manifest.json').read_text(encoding='utf8'))
    if doc.get('schema') != 'v3a25_display_bundle_v1' or any(doc.get(k) is not False for k in FLAGS):
        raise ValueError('显示包身份／正式门错误')
    if (doc.get('raw_hz'),doc.get('processing_hz'),doc.get('duration_seconds'),doc.get('beta_int')) != (50,25,60,32212255):
        raise ValueError('显示包采样参数不符')
    if doc.get('static_zip_sha256') != STATIC_ZIP_SHA or digest(root/'static/pilot25-manifest.json') != STATIC_MANIFEST_SHA:
        raise ValueError('静止基包身份不符')
    files = doc.get('files',{})
    if not REQUIRED <= files.keys(): raise ValueError('显示包缺必要文件')
    for name,sha in files.items():
        path = local(root,name)
        if not path.is_file() or digest(path) != sha: raise ValueError('文件缺失或SHA256不符：'+name)
    old = validate_static(root/'static')
    if not {'static/'+name for name in old['files']} <= files.keys(): raise ValueError('缺静止包闭包')
    audit = json.loads((root/'evidence/static-capture-audit.json').read_text(encoding='utf8'))
    if (audit.get('archive_sha256') != STATIC_ZIP_SHA or audit.get('static_capture_verified') is not True
            or audit.get('raw_rows') != 3008 or audit.get('result_rows') != 1504
            or not all(audit.get('gates',{}).values()) or any(audit.get(k) is not False for k in FLAGS)):
        raise ValueError('静止前置证据不完整')
    return doc


def verify_imports(root):
    root = Path(root).resolve()
    for name in ('display25.runner','display25.assessment','display25.render','pilot25.board',
                 'heart_v3a.live.board','heart_v3a.live.session','v3a_25hz_live.session',
                 'v3a_25hz_live.view','v3a_rate25.frontend','peak_chain'):
        importlib.import_module(name)
    prefixes = ('display25','pilot25','heart_v2','heart_v3a','v3a_25hz_live','v3a_rate25','rate25_tools')
    for name,module in tuple(sys.modules.items()):
        if name.split('.')[0] in prefixes or name in ('peak_chain','peak_timing','heart_axi_live','heart_axi_capture_50hz'):
            file = getattr(module,'__file__',None)
            if file is not None and not Path(file).resolve().is_relative_to(root):
                raise ValueError('检测到旧内核串包，请在新目录新建Notebook并重启内核：'+name)
