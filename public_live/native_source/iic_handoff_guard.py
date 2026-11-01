"""Cold identity for an additive IIC-only candidate; inherited gates unchanged."""
import json
from pathlib import Path

if __package__:
    from .yuyv_joint_guard import verify_package as verify_previous, assess_joint as previous_assess
    from .yuyv_joint_guard import sha, write_new, notebook_code_hash, FLAGS
else:
    from yuyv_joint_guard import verify_package as verify_previous, assess_joint as previous_assess
    from yuyv_joint_guard import sha, write_new, notebook_code_hash, FLAGS

MANIFEST = 'iic-handoff-manifest.json'
NOTEBOOK = 'IicHandoffJoint60.ipynb'
BASE_SHA = 'd1edb584a114472e803684dbb6927b9caaf76afd7b756b0dac49b56cbe6d8901'
EXTRAS = {'iic_handoff.c', 'iic_handoff_impl.h', 'iic_handoff_selftest.c', 'iic_handoff.py',
    'iic_handoff_binding.py', 'iic_handoff_build.py', 'iic_handoff_guard.py',
    'iic_handoff_worker.py', 'run_iic_handoff.py', 'README_IIC_HANDOFF.md'}


def verify_package(root):
    root = Path(root); previous = verify_previous(root); path = root / MANIFEST
    if path.is_symlink(): raise ValueError('handoff manifest symlink forbidden')
    doc = json.loads(path.read_text('utf-8'))
    if (doc.get('schema') != 'v3b25_iic_handoff_package_v1'
        or doc.get('base_manifest_sha256') != BASE_SHA or sha(root / 'yuyv-joint-manifest.json') != BASE_SHA
        or set(doc.get('files', {})) != EXTRAS
        or tuple(doc.get(k) for k in ('raw_hz', 'processing_hz', 'video_target_fps', 'formal_seconds',
            'warmup_slots', 'transaction_timeout_seconds', 'stop_timeout_seconds')) != (25, 25, 5, 60, 700, .05, .05)
        or any(doc.get(k) is not True for k in ('pairing_policy_unchanged', 'gc_policy_unchanged', 'processing_exit_strategy_unchanged'))
        or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('handoff scope/identity changed')
    for name, expected in doc['files'].items():
        p = root / name
        if p.is_symlink() or not p.is_file() or sha(p) != expected: raise ValueError('handoff source changed: ' + name)
    if (root / NOTEBOOK).is_symlink() or notebook_code_hash(root / NOTEBOOK) != doc.get('notebook_code_sha256'):
        raise ValueError('handoff Notebook code changed')
    return dict(previous, iic_handoff_manifest_sha256=sha(path), entry='manual_iic_handoff_joint60',
        iic_complete_read=True, hardware_accessed=False, iic_handoff_joint60_completed=False)


def assess_joint(original, owner, *, build, inputs_unchanged, wrapper_error=None):
    result = previous_assess(original, owner, build=build, inputs_unchanged=inputs_unchanged, wrapper_error=wrapper_error)
    iic = owner.get('iic') or {}
    result['checks']['complete_read_binding'] = bool(iic.get('complete_register_read') is True
        and iic.get('state_snapshot_fields') == 21 and type(iic.get('complete_read_calls')) is int
        and iic['complete_read_calls'] > 0 and iic.get('split_receive_calls') == 0)
    result.update(schema='v3b25_iic_handoff_joint60_v1', iic_implementation_unchanged=False,
        pairing_policy_unchanged=True, gc_policy_unchanged=True,
        yuyv_joint60_completed=all(result['checks'].values()),
        iic_handoff_joint60_completed=all(result['checks'].values()),
        scope_cn='仅IIC完整寄存器读取/返回状态/直接缓冲交接变更；原50ms、配对、GC和退出策略保留。25/25Hz心率＋5fps新PL视频共同60秒；不是准确率、DDR或完整V3B验收。')
    return result
