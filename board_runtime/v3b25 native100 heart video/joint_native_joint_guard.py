"""Cold source identity and added IIC gate; never replaces original audits."""
import json
from pathlib import Path
if __package__:
    from .joint_iic_native_guard import verify_native,sha,write_new,notebook_code_hash,FLAGS
else:
    from joint_iic_native_guard import verify_native,sha,write_new,notebook_code_hash,FLAGS

BASE_SHA='adafb66f6c85f228f69ddb0ec905f6cdeda004f206f090591eaed02c04e42852'
MANIFEST='native-joint60-manifest.json';NOTEBOOK='NativeJoint60.ipynb'
EXTRAS={'joint_native_joint_binding.py','joint_native_joint_worker.py','joint_native_joint_guard.py',
        'run_joint_native_joint.py','README_NATIVE_JOINT60.md'}


def verify_native_joint(root):
    root=Path(root);base=verify_native(root);path=root/MANIFEST
    if path.is_symlink():raise ValueError('joint manifest symlink forbidden')
    doc=json.loads(path.read_text(encoding='utf-8'))
    if (doc.get('schema')!='v3b25_native_joint60_package_v1' or doc.get('base_manifest_sha256')!=BASE_SHA or
        sha(root/'joint-iic-native-manifest.json')!=BASE_SHA or set(doc.get('files',{}))!=EXTRAS or
        tuple(doc.get(k) for k in ('adc_hz','raw_hz','processing_hz','fifo_sample_average','video_target_fps','formal_seconds'))!=(50,25,25,2,5,60) or
        doc.get('shared_release_gate')!='native_iic_and_original_dma_video_resources' or
        any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('native joint scope changed')
    for name,digest in doc['files'].items():
        target=root/name
        if target.is_symlink() or not target.is_file() or sha(target)!=digest:raise ValueError('joint source changed: '+name)
    if (root/NOTEBOOK).is_symlink() or notebook_code_hash(root/NOTEBOOK)!=doc.get('notebook_code_sha256'):
        raise ValueError('native joint Notebook code changed')
    return dict(base,entry='manual_native_joint60',formal_seconds=60,video_target_fps=5,
        raw_hz=25,processing_hz=25,native_joint_manifest_sha256=sha(path),native_joint60_completed=False)


def assess_native_joint(original,owner,*,build,inputs_unchanged,wrapper_error=None):
    iic=owner.get('iic') or {};cleanup=owner.get('cleanup') or {};dma=cleanup.get('dma') or {}
    checks=dict(original_snapshot=original.get('snapshot_candidate_completed') is True,
        original_joint60=original.get('joint_60s_pilot_completed') is True and original.get('wrapper_error') is None,
        native_iic=iic.get('mode')=='normal_native_c' and iic.get('fault') is None and
            iic.get('active_call') is False and iic.get('register_selection_pending') is False,
        transactions=type(iic.get('transactions_started')) is int and iic['transactions_started']>0 and
            iic['transactions_started']==iic.get('transactions_completed'),
        iic_quiesced=(iic.get('quiescence') or {}).get('iic_quiesced') is True and
            (cleanup.get('iic') or {}).get('iic_quiesced') is True,
        native_build=bool(build.get('library_sha256')) and
            (iic.get('native_build') or {}).get('library_sha256')==build.get('library_sha256'),
        actual_cleanup=cleanup.get('cleanup_complete') is True and owner.get('actual_lease_released') is True and
            owner.get('quarantine_required') is False and not cleanup.get('errors') and
            set(dma)=={'vision_dma','hdmi_vdma'} and all(d.get('halted') is True and not d.get('error_bits') for d in dma.values()),
        inputs_unchanged=inputs_unchanged is True,no_wrapper_error=wrapper_error is None)
    return dict(schema='v3b25_native_joint60_trial_v1',native_joint60_completed=all(checks.values()),
        checks=checks,wrapper_error=wrapper_error,screen_dynamic_observed=None,**FLAGS,
        scope_cn='原生IIC接回25/25Hz心率＋5fps共同60秒小试；保留原全部判定。不是50Hz、15fps、严格实时、准确率、DDR或完整V3B验收。')
