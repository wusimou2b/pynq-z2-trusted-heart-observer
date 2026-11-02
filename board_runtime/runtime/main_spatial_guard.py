"""Frozen hybrid plus exact new main/spatial release and additive source identity."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

if __package__:
    from .hybrid_guard import verify_package as verify_baseline
    from .main_heart_guard import verify_release
    from .spatial_camera_guard import notebook_identity
else:
    from hybrid_guard import verify_package as verify_baseline
    from main_heart_guard import verify_release
    from spatial_camera_guard import notebook_identity

MANIFEST='main-spatial-manifest.json'
BOOK='MainSpatial25.ipynb'


def verify_package(root,expected_manifest_sha=None):
    root=Path(root).resolve()
    base=verify_baseline(root,expected_manifest_sha)
    path=root/MANIFEST
    doc=json.loads(path.read_bytes())
    if (doc.get('schema')!='v3b25_main_spatial_hybrid_package_v1'
        or doc.get('baseline_manifest_sha256')!=base['manifest_sha256']
        or doc.get('rates')!=[25,25,5] or doc.get('grid')!=[4,3]
        or doc.get('display_layout')!='camera_bpm_strip_v1'
        or doc.get('protections')!=dict(warmup=700,ready_seconds=60,startup_seconds=180,
            step_seconds=1,exit_seconds=1,freshness_ns=1000000000,main_command_seconds=.020)
        or doc.get('automatic_retry') is not False):
        raise ValueError('main/spatial package scope differs')
    for name,pin in doc['files'].items():
        p=root/name
        if Path(name).is_absolute() or '..' in Path(name).parts or ':' in name or '\\' in name or p.is_symlink():
            raise ValueError('unsafe integrated member')
        if hashlib.sha256(p.read_bytes()).hexdigest()!=pin:
            raise ValueError('integrated member hash differs: '+name)
    if notebook_identity(root/BOOK)!=doc['notebook_identity_sha256']:
        raise ValueError('integrated Notebook source differs')
    release=verify_release(root/'hardware')
    identity=json.loads((root/'hardware/main-spatial-integration.json').read_bytes())
    if (identity.get('local_verified') is not True or identity.get('spatial_vlnv')!='v3b25.local:vision:vision_spatial_axi_lite:2.0'
        or identity.get('pair')!=release['files']):
        raise ValueError('integrated local release evidence missing')
    tree=ET.parse(root/'hardware/heart_v3b25_main.hwh')
    if tree.find("./MODULES/MODULE[@FULLNAME='/vision_0']").get('VLNV')!=identity['spatial_vlnv']:
        raise ValueError('old spatial version in integrated hardware')
    return dict(base,integration_manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                main_spatial_local_verified=True,hardware_accessed=False)
