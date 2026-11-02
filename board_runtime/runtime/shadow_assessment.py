"""Explicit spatial-v2 gates; legacy source/result identities are never forged."""
from collections import Counter, OrderedDict
import csv
import json
import math
from pathlib import Path
from types import SimpleNamespace as NS

if __package__:
    from .yuyv_joint_guard import assess_yuyv_video as _legacy_assess
    from . import yuyv_joint_guard as legacy_video
    from .continuous_control import audit_artifacts as _legacy_artifacts
    from .joint_startup import replace_attribute
    from .shadow_video_core import VideoCandidate, profile
    from .shadow_fusion import fuse
    from .roi_motion_core import integer
    from .shadow_imu import evidence
else:
    from yuyv_joint_guard import assess_yuyv_video as _legacy_assess
    import yuyv_joint_guard as legacy_video
    from continuous_control import audit_artifacts as _legacy_artifacts
    from joint_startup import replace_attribute
    from shadow_video_core import VideoCandidate, profile
    from shadow_fusion import fuse
    from roi_motion_core import integer
    from shadow_imu import evidence


def assess_spatial_video(report):
    gates = _legacy_assess(report)
    identity = (report.get('identity') or {}).get('joint_identity') or {}
    gates['joint_identity'] = bool(identity.get('nlms_axi_0') == dict(id=0x4e4c3304, version=0x10000)
        and identity.get('vision_0') == dict(id=0x56334232, version=0x20000)
        and identity.get('metadata') == dict(windows=15, vdma_frame_stores=4, writeback_s2mm_only=True, spatial_version=0x20000))
    post = report.get('post_verification') or {}
    rows = post.get('spatial_rows') or []
    gates['spatial_post_check'] = bool(post.get('spatial_compared_frames') == len(rows) == 2
        and [r.get('source_sequence') for r in rows] == [0, 1] and all(r.get('mismatches') == {} for r in rows))
    return gates


def _available(row, now_ns, *, video_ns=None):
    if row is None:
        return False
    integer(row['sequence'], 'IMU sequence')
    integer(row['processing_finished_ns'], 'processing_finished_ns')
    integer(row['observed_ns'], 'observed_ns', row['processing_finished_ns'], now_ns)
    if row['epoch'] is not None:
        integer(row['epoch'], 'IMU epoch', high=0xffffffff)
    if type(row['valid']) is not bool:
        raise ValueError('IMU validity not bool')
    source = row['source_ns']
    if source is not None:
        integer(source, 'IMU source', high=row['processing_finished_ns'])
        if video_ns is not None and source > video_ns:
            raise ValueError('future IMU selected')
    if not row['valid']:
        if row['label'] != 'UNKNOWN' or row['reason'] == 'ok':
            raise ValueError('invalid IMU labelled valid')
        return False
    if (row['epoch'] is None or source is None or row['reason'] != 'ok'
        or row['label'] not in ('STATIC','LIGHT','HEAVY') or type(row['rms_g']) not in (int,float)
        or not math.isfinite(row['rms_g']) or row['rms_g'] < 0):
        raise ValueError('IMU selected payload invalid')
    return 0 <= now_ns-source <= 250_000_000


def _check_match(match, timestamp_ns, now_ns):
    candidate, current = match['candidate'], match['current']
    available = _available(candidate, now_ns, video_ns=timestamp_ns)
    current_available = _available(current, now_ns)
    age = now_ns-candidate['source_ns'] if candidate and candidate['source_ns'] is not None else None
    delta = timestamp_ns-candidate['source_ns'] if candidate and candidate['source_ns'] is not None else None
    reason = ('no_past_source' if candidate is None else candidate['reason'] if not candidate['valid']
              else 'imu_stale' if age > 250_000_000 else 'unmatched' if delta > 250_000_000 else 'ok')
    paired = available and delta <= 250_000_000
    if (match['pair_available'] is not paired or match['current_available'] is not current_available
        or match['label'] != (candidate['label'] if paired else 'UNKNOWN')
        or match['age_ns'] != age or match['delta_ns'] != delta or match['reason'] != reason):
        raise ValueError('saved IMU time/availability differs')
    integer(match['generation'], 'IMU generation')


def audit_shadow_journal(path):
    classifier = VideoCandidate()
    count, last_generation = 0, None
    modes, labels, errors = Counter(), Counter(), []
    try:
        with Path(path).open(encoding='utf-8') as stream:
            for line in stream:
                row = json.loads(line)
                saved = row['shadow']
                before = integer(saved['imu_generation_before'], 'IMU generation before')
                if last_generation is not None:
                    if before < last_generation:
                        raise ValueError('shadow generation rollback')
                    if before != last_generation:
                        classifier.clear()
                if row['vision']['source_sequence'] != row['source_sequence'] or row['read_completed_ns'] != row['vision']['timestamp_ns']:
                    raise ValueError('shadow source identity differs')
                now = saved['decision_ns']
                wanted = classifier.consume(row['vision'], now_ns=now)
                imu = saved['imu']
                _check_match(imu, wanted['timestamp_ns'], now)
                if imu['generation'] < before:
                    raise ValueError('IMU generation precedes decision')
                if imu['generation'] != before and wanted['reason'] != 'epoch_changed':
                    classifier.clear()
                    wanted.update(label='UNKNOWN', prediction_reason='imu_epoch_changed', window=[], candidate=None, candidate_count=0)
                if wanted != saved['video']:
                    raise ValueError('saved video candidate differs from frozen replay')
                expected = fuse(video=wanted['label'], imu=imu['label'], pair_available=imu['pair_available'],
                                unmatched=bool(not imu['pair_available'] and imu['current_available']))
                if (any(saved[k] != v for k, v in expected.items()) or saved['rule_sha256'] != profile()['sha256']
                    or saved['schema'] != 'v3b25_shadow_fusion_v1'):
                    raise ValueError('saved shadow decision differs')
                last_generation = imu['generation']
                count += 1
                modes[saved['evidence_mode']] += 1
                labels[saved['label']] += 1
    except Exception as exc:
        errors.append(dict(row=count, type=type(exc).__name__, message=str(exc)))
    return dict(passed=not errors and count >= 3, rows=count, mismatches=errors, modes=dict(modes), labels=dict(labels),
                actual_imu_origin_crosschecked=False, scope='scalar causal/profile replay only; not raw-CSV origin or accuracy')


def audit_shadow_artifacts(directory, summary, owner):
    writers_stopped = bool((owner.get('video') or {}).get('thread_exited') is True
                           and summary.get('queues_drained') is True)
    if not writers_stopped:
        return dict(checks=dict(writers_stopped=False), journals_read=False,
                    errors=[dict(type='RuntimeError',message='writer exit/drain not confirmed; journals not read')],
                    heart_control_enabled=False, accuracy_verified=False)
    # Upgrade only the new, explicitly scoped vision identity gate; preserve all old common gates.
    with replace_attribute(legacy_video, 'assess_yuyv_video', assess_spatial_video):
        result = _legacy_artifacts(directory, summary, owner)
    shadow = audit_shadow_journal(Path(directory)/'video/frames.jsonl')
    origins = audit_imu_origins(directory)
    result['checks']['shadow_scalar_replay'] = shadow['passed']
    result['checks']['shadow_imu_origins'] = origins['passed']
    result['checks']['writers_stopped'] = True
    result.update(shadow_journal=shadow, video_identity_scope='spatial_v2 only; not legacy YUYV-v1 acceptance',
                  imu_origins=origins, journals_read=True, heart_control_enabled=False, accuracy_verified=False)
    return result


class _CsvCursor:
    """Post-stop merge reader; fixed256 row cache, not a live acquisition cache."""
    def __init__(self, stream):
        self.reader = iter(csv.DictReader(stream))
        self.index = -1
        self.cache = OrderedDict()

    def get(self, sequence):
        integer(sequence, 'CSV sequence')
        while self.index < sequence:
            row = next(self.reader)
            index = int(row['sequence'])
            if index <= self.index:
                raise ValueError('capture CSV sequence rollback')
            self.index = index
            self.cache[index] = row
            if len(self.cache) > 256:
                self.cache.popitem(last=False)
        if sequence not in self.cache:
            raise ValueError('IMU source missing or outside stopped-audit merge cache')
        return self.cache[sequence]


def audit_imu_origins(directory):
    directory = Path(directory)
    checked, errors = 0, []
    try:
        with (directory/'capture/raw.csv').open(encoding='utf-8', newline='') as raw_stream, \
             (directory/'capture/results.csv').open(encoding='utf-8', newline='') as result_stream, \
             (directory/'video/frames.jsonl').open(encoding='utf-8') as journal:
            raw, results = _CsvCursor(raw_stream), _CsvCursor(result_stream)
            for line in journal:
                imu = json.loads(line)['shadow']['imu']
                for entry in (imu['candidate'], imu['current']):
                    if entry is None:
                        continue
                    sequence = entry['sequence']
                    r, s = raw.get(sequence), results.get(sequence)
                    if int(s['source_first']) != sequence or int(s['source_last']) != sequence:
                        raise ValueError('IMU source endpoints differ from processed result')
                    payload = dict(sequence=sequence,
                        mpu_read_completed_ns=int(r['mpu_read_completed_ns']) if r['mpu_read_completed_ns'] else '',
                        pair_ok=r['pair_ok']=='True', accel_valid=r['accel_valid']=='True')
                    if r['pair_ok'] not in ('True','False') or r['accel_valid'] not in ('True','False'):
                        raise ValueError('capture IMU bool not explicit')
                    if s['motion_ready'] not in ('True','False') or s['valid'] not in ('True','False'):
                        raise ValueError('processed IMU bool not explicit')
                    frame = NS(sequence=int(s['sequence']), motion=s['motion'] or None,
                        motion_ready=s['motion_ready']=='True', valid=s['valid']=='True',
                        motion_rms_g=float(s['motion_rms_g']) if s['motion_rms_g'] else None)
                    record = NS(saved=NS(record=NS(raw=payload)),
                        runtime=NS(frame=frame, pl_epoch=int(s['pl_epoch']) if s['pl_epoch'] else None),
                        processing_finished_ns=int(s['processing_finished_ns']))
                    if evidence(record, entry['observed_ns']) != entry:
                        raise ValueError('shadow IMU does not match raw/result CSV')
                    checked += 1
    except Exception as exc:
        errors.append(dict(entry=checked, type=type(exc).__name__, message=str(exc)))
    passed = not errors and checked > 0
    return dict(passed=passed, checked_entries=checked, mismatches=errors,
                actual_imu_origin_crosschecked=passed, scope='stopped raw/result CSV origin; not accuracy')
