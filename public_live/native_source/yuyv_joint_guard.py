"""Cold identity and applicable YUYV evidence gates; heart/common gates stay."""
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path

if __package__:
    from .joint_native_joint_guard import verify_native_joint, sha, write_new, notebook_code_hash, FLAGS
    from .run_yuyv_video import verify_package as verify_video, SOURCES
    from .joint_startup import replace_attribute
else:
    from joint_native_joint_guard import verify_native_joint, sha, write_new, notebook_code_hash, FLAGS
    from run_yuyv_video import verify_package as verify_video, SOURCES
    from joint_startup import replace_attribute

MANIFEST = 'yuyv-joint-manifest.json'
NOTEBOOK = 'YuyvJoint60.ipynb'
EXTRAS = {'yuyv_joint_binding.py', 'yuyv_joint_guard.py', 'yuyv_joint_worker.py',
          'run_yuyv_joint.py', 'README_YUYV_JOINT.md'}
VIDEO_FILES = SOURCES | {'YuyvVideo.ipynb', 'yuyv-video-manifest.json'}
BASE_SHA = '1ba0d2c4c64226b7bd7a89d42f139db38ce43bdb818c021fed5af3b64995ee75'
VIDEO_SHA = 'b91add10c68ebab68d6dfa0238bb65b4af0543acef8e8cb53337626dae36c9a8'
DMA_NAMES = {'vision_dma', 'hdmi_vdma', 'display_dma'}


def verify_package(root):
    root = Path(root); previous = verify_native_joint(root); verify_video(root)
    path = root / MANIFEST
    if path.is_symlink(): raise ValueError('YUYV joint manifest symlink forbidden')
    doc = json.loads(path.read_text('utf-8'))
    if (doc.get('schema') != 'v3b25_yuyv_joint_package_v1'
        or sha(root / 'native-joint60-manifest.json') != BASE_SHA or doc.get('base_manifest_sha256') != BASE_SHA
        or sha(root / 'yuyv-video-manifest.json') != VIDEO_SHA or doc.get('video_manifest_sha256') != VIDEO_SHA
        or set(doc.get('files', {})) != EXTRAS | VIDEO_FILES
        or tuple(doc.get(k) for k in ('raw_hz', 'processing_hz', 'video_target_fps', 'formal_seconds', 'warmup_slots')) != (25, 25, 5, 60, 700)
        or doc.get('iic_implementation_unchanged') is not True or doc.get('processing_exit_strategy_unchanged') is not True
        or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError('YUYV joint scope/identity changed')
    for name, expected in doc['files'].items():
        p = root / name
        if p.is_symlink() or not p.is_file() or sha(p) != expected: raise ValueError('YUYV joint source changed: ' + name)
    if (root / NOTEBOOK).is_symlink() or notebook_code_hash(root / NOTEBOOK) != doc.get('notebook_code_sha256'):
        raise ValueError('YUYV joint Notebook code changed')
    return dict(previous, yuyv_joint_manifest_sha256=sha(path), hardware_accessed=False,
                yuyv_joint60_completed=False, entry='manual_yuyv_joint60')


def _post_ok(post, n):
    rows = post.get('rows') or []
    return bool(post.get('attempted') is True and post.get('after_hardware_cleanup') is True
        and post.get('compared_frames') == len(rows) == 2 and post.get('total_frames') == n
        and post.get('matched') is True and post.get('all_frames_verified') is False and post.get('images_saved') is False
        and [r.get('source_sequence') for r in rows] == [0, 1]
        and all(r.get('pixel_mismatch_bytes') == 0 and r.get('stats_mismatches') == {} for r in rows))


def assess_yuyv_video(report):
    m = report.get('metrics') or {}; c = report.get('cleanup') or {}; j = c.get('joint') or {}
    identity = report.get('identity') or {}; core = identity.get('joint_identity') or {}; dma = j.get('dma') or {}
    n = m.get('completed_frames', 0)
    return dict(
        no_fault=report.get('fault') is None and report.get('publication_error') is None,
        joint_identity=(core.get('nlms_axi_0') or {}).get('id') == 0x4e4c3304
            and (core.get('vision_0') or {}).get('id') == 0x56334231 and (core.get('metadata') or {}).get('windows') == 15,
        pl_color_writeback=identity.get('raw_camera_format') == 'YUYV' and identity.get('hdmi_format') == 'BGRX32'
            and identity.get('hdmi_stride') == 2560,
        one_download=j.get('download_attempts') == 1,
        exact_counts=n >= 3 and n == m.get('records_saved') == c.get('captured_frames') == c.get('submitted_frames') == c.get('vision_completed_frames'),
        reference_scope=report.get('reference_mode') == 'two_frames_checked_only_after_hardware_cleanup'
            and report.get('all_frames_reference_verified') is False and report.get('formal_reference_calls') == 0,
        post_check=_post_ok(report.get('post_verification') or {}, n),
        cleanup=c.get('cleanup_complete') is True and c.get('quarantine_required') is False
            and j.get('cleanup_complete') is True and set(dma) == DMA_NAMES
            and all(v.get('halted') is True and v.get('error_bits') == 0 for v in dma.values())
            and all(c.get(k) is True for k in ('buffers_released', 'actual_lease_released', 'camera_released', 'hdmi_closed')),
        inputs_unchanged=report.get('inputs_unchanged') is True,
        formal_flags_false=all(report.get(k) is False for k in FLAGS))


def audit_yuyv(directory, report):
    checks = dict(parse_hash=False, counts=False, source=False, complete_writeback=False, cache=False, reference=False)
    result = dict(checks=checks, rows=0, error=None)
    try:
        path = Path(directory) / 'frames.jsonl'; data = path.read_bytes()
        rows = [json.loads(line) for line in data.decode('utf-8').splitlines()]; n = len(rows); result['rows'] = n
        m = report.get('metrics') or {}
        checks['parse_hash'] = bool(data.endswith(b'\n') and sha(path) == report.get('frames_sha256'))
        checks['counts'] = bool(n >= 3 and n == m.get('completed_frames') == m.get('records_saved')
            and sum(r['vision']['difference_valid'] for r in rows) == m.get('valid_difference_frames'))
        source = bool(n and len({r['vision']['epoch'] for r in rows}) == 1)
        previous = None
        for i, row in enumerate(rows):
            v = row['vision']; timestamp = row['read_completed_ns']; elapsed = None if i == 0 else timestamp - previous
            valid = i > 0 and 0 < elapsed <= 250_000_000
            source &= bool(row['source_sequence'] == v['source_sequence'] == v['frame_index'] == i
                and v['timestamp_ns'] == timestamp and type(timestamp) is int and (i == 0 or elapsed > 0)
                and v['source_previous_sequence'] == (i - 1 if i else None) and v['pair_elapsed_ns'] == elapsed
                and v['missed_frames'] == 0 and v['pixel_count'] == 19200
                and v['difference_valid'] is valid and v['reason'] == ('first_frame' if not i else 'ok' if valid else 'timestamp_gap')
                and 0 <= v['luma_min'] <= v['luma_max'] <= 255
                and v['luma_min'] * 19200 <= v['luma_sum'] <= v['luma_max'] * 19200 and row['hdmi_submitted'] is True)
            source &= bool(0 <= v['diff_max'] <= 255 and 0 <= v['diff_sum'] <= v['diff_max'] * 19200
                if valid else v['diff_sum'] is None and v['diff_max'] is None)
            previous = timestamp
        checks['source'] = bool(source)
        checks['complete_writeback'] = bool(n and all(r['vision']['writeback_bytes'] == 1228800 for r in rows))
        checks['cache'] = bool(n and all(type(r['vision']['destination_coherent']) is bool
            and r['vision']['explicit_cache_sync'] is (not r['vision']['destination_coherent']) for r in rows))
        checks['reference'] = _post_ok(report.get('post_verification') or {}, n)
    except Exception as exc: result['error'] = dict(type=type(exc).__name__, message=str(exc))
    return result


@contextmanager
def install_assessment(pair):
    if __package__: from . import joint_concurrent_guard as original
    else: import joint_concurrent_guard as original
    hashes = {'heart_v3b25.bit': pair['heart_v3b25_yuyv.bit'], 'heart_v3b25.hwh': pair['heart_v3b25_yuyv.hwh']}
    with ExitStack() as stack:
        for key, value in (('PAIR_HASHES', hashes), ('audit_pack', audit_yuyv), ('assess_pack', assess_yuyv_video)):
            stack.enter_context(replace_attribute(original, key, value))
        yield


def assess_joint(original, owner, *, build, inputs_unchanged, wrapper_error=None):
    iic = owner.get('iic') or {}; cleanup = owner.get('cleanup') or {}; dma = cleanup.get('dma') or {}
    checks = dict(
        original_snapshot=original.get('snapshot_candidate_completed') is True,
        original_joint60=original.get('joint_60s_pilot_completed') is True and original.get('wrapper_error') is None,
        native_iic=iic.get('mode') == 'normal_native_c' and iic.get('fault') is None
            and iic.get('active_call') is False and iic.get('register_selection_pending') is False,
        transactions=type(iic.get('transactions_started')) is int and iic['transactions_started'] > 0
            and iic['transactions_started'] == iic.get('transactions_completed'),
        iic_quiesced=(iic.get('quiescence') or {}).get('iic_quiesced') is True
            and (cleanup.get('iic') or {}).get('iic_quiesced') is True,
        native_build=bool(build.get('library_sha256'))
            and (iic.get('native_build') or {}).get('library_sha256') == build.get('library_sha256'),
        actual_cleanup=cleanup.get('cleanup_complete') is True and owner.get('actual_lease_released') is True
            and owner.get('quarantine_required') is False and not cleanup.get('errors') and set(dma) == DMA_NAMES
            and all(v.get('halted') is True and not v.get('error_bits') for v in dma.values()),
        inputs_unchanged=inputs_unchanged is True, no_wrapper_error=wrapper_error is None)
    return dict(schema='v3b25_yuyv_joint60_trial_v1', yuyv_joint60_completed=all(checks.values()),
        checks=checks, wrapper_error=wrapper_error, screen_dynamic_observed=None, **FLAGS,
        iic_implementation_unchanged=True, processing_exit_strategy_unchanged=True,
        scope_cn='仅视频通路替换为新PL颜色/ROI/写回；25/25Hz心率与5fps共同60秒候选。原IIC/GC/保护/退出策略不变；不是准确率、DDR、15fps或完整V3B验收。')
