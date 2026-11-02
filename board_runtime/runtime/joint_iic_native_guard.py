"""Cold identity of new native files; the published Python IIC files stay exact."""
import json
from pathlib import Path
if __package__:
    from .joint_iic_guard import verify_iic,sha,write_new,notebook_code_hash,FLAGS
else:
    from joint_iic_guard import verify_iic,sha,write_new,notebook_code_hash,FLAGS

BASE_SHA='a6ff3b8e585a320e92bea280b032f8c1f3990b2567d1e42cbf9db41ec703b775'
MANIFEST='joint-iic-native-manifest.json'
NOTEBOOK='NativeIicSensor5.ipynb'
EXTRAS={'joint_iic_native.c','joint_iic_native.py','joint_iic_native_build.py',
        'joint_iic_native_selftest.c','joint_iic_native_binding.py','joint_iic_native_guard.py',
        'run_joint_iic_native.py','README_IIC_NATIVE.md'}


def verify_native(root):
    root=Path(root);base=verify_iic(root);path=root/MANIFEST
    if path.is_symlink():raise ValueError('native manifest symlink forbidden')
    doc=json.loads(path.read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_native_iic_package_v1' or doc.get('entry')!='manual_native_sensor5' or
        doc.get('base_manifest_sha256')!=BASE_SHA or sha(root/'joint-iic-manifest.json')!=BASE_SHA or
        set(doc.get('files',{}))!=EXTRAS or
        tuple(doc.get(k) for k in ('adc_hz','raw_hz','processing_target_hz','fifo_sample_average',
             'formal_seconds','transaction_timeout_seconds','stop_timeout_seconds'))!=(50,25,25,2,5,.05,.05) or
        doc.get('overlay_check_scope')!='before_and_after_native_call_not_each_MMIO' or
        doc.get('private_existing_compiler_only') is not True or
        any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('native IIC candidate scope changed')
    for name,digest in doc['files'].items():
        target=root/name
        if target.is_symlink() or not target.is_file() or sha(target)!=digest:
            raise ValueError('native IIC source changed: '+name)
    if (root/NOTEBOOK).is_symlink() or notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):
        raise ValueError('native IIC Notebook code changed')
    return dict(base,entry='manual_native_sensor5',native_iic_manifest_sha256=sha(path),
                native_build_required=True,formal_seconds=5,hardware_accessed=False,
                overlay_check_scope=doc['overlay_check_scope'])
