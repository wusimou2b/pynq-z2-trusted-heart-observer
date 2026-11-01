"""Stdlib-only identity/scope of the five-second sensor transport candidate."""
import json
from pathlib import Path
if __package__:
    from .joint_snapshot_guard import verify_snapshot,sha,write_new,notebook_code_hash,FLAGS as BASE_FLAGS
else:
    from joint_snapshot_guard import verify_snapshot,sha,write_new,notebook_code_hash,FLAGS as BASE_FLAGS

BASE_SHA='83c80b26c0b698037ae27eb5a14079cbb49439c4ea0fce4cac83f0c2c195eb2f'
MANIFEST='joint-iic-manifest.json'
NOTEBOOK='IicSensor5.ipynb'
EXTRAS={'joint_iic.py','joint_iic_binding.py','joint_iic_probe.py','joint_iic_guard.py',
        'run_joint_iic.py','README_IIC.md'}
FLAGS=dict(BASE_FLAGS,concurrent60_passed=False)


def verify_iic(root):
    root=Path(root);base=verify_snapshot(root)
    path=root/MANIFEST
    if path.is_symlink():raise ValueError('IIC manifest symlink forbidden')
    doc=json.loads(path.read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_iic_sensor5_package_v1' or
        sha(root/'joint-snapshot-manifest.json')!=BASE_SHA or doc.get('base_manifest_sha256')!=BASE_SHA or
        set(doc.get('files',{}))!=EXTRAS or doc.get('entry')!='manual_sensor5' or
        tuple(doc.get(k) for k in ('adc_hz','raw_hz','processing_target_hz','fifo_sample_average',
              'formal_seconds','transaction_timeout_seconds','stop_timeout_seconds'))!=(50,25,25,2,5,.050,.050) or
        any(doc.get(k) is not False for k in FLAGS) or
        any(doc.get(k) is not False for k in ('camera_started','hdmi_started','ps_algorithm_started'))):
        raise ValueError('IIC candidate scope changed')
    for name,digest in doc['files'].items():
        target=root/name
        if target.is_symlink() or not target.is_file() or sha(target)!=digest:
            raise ValueError('IIC source changed: '+name)
    if (root/NOTEBOOK).is_symlink() or notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):
        raise ValueError('IIC Notebook code changed')
    return dict(base,iic_manifest_sha256=sha(path),entry='manual_sensor5',
                formal_seconds=5,reference_joint_formal_seconds=base['formal_seconds'],
                sensor_io_trial_complete=False,hardware_accessed=False,
                configured_effective_raw_hz=25,camera_started=False,hdmi_started=False,ps_algorithm_started=False)
