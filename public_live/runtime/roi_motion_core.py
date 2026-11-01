"""Scalar-only fixed-ROI motion contract. No drivers, images or heart imports."""
from collections import deque
import hashlib
import json
import math
from statistics import median

ROI = [80, 60, 240, 180]
PAIR_NS = 250_000_000
LABELS = ('STATIC', 'LIGHT', 'HEAVY')
SCHEMA = 'v3b25_roi_motion_profile_v1'


def integer(value, name, low=0, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError('invalid integer: ' + name)
    return value


def score_value(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 255:
        raise ValueError('score must be finite in 0..255')
    return value


class SourceAdapter:
    """Validate actual YuyvPort metadata, retaining only its previous source."""
    def __init__(self):
        self.previous = None

    def consume(self, stats, *, now_ns):
        required = ('epoch', 'source_sequence', 'timestamp_ns', 'source_previous_sequence',
                    'pair_elapsed_ns', 'pixel_count', 'difference_valid', 'diff_sum', 'diff_max',
                    'reason', 'missed_frames')
        if not isinstance(stats, dict) or any(k not in stats for k in required):
            raise ValueError('incomplete PL motion metadata')
        ep = integer(stats['epoch'], 'epoch', high=0xffffffff)
        seq = integer(stats['source_sequence'], 'source_sequence', high=0xffffffff)
        ts = integer(stats['timestamp_ns'], 'timestamp_ns')
        integer(now_ns, 'now_ns', ts)
        if stats['pixel_count'] != 19200 or type(stats['pixel_count']) is not int:
            raise ValueError('ROI pixel count changed')
        if type(stats['difference_valid']) is not bool:
            raise ValueError('invalid difference flag')
        prev = self.previous
        changed = prev is not None and ep != prev[0]
        if prev is not None and ts <= prev[2]:
            raise ValueError('source time must increase')
        if prev is None or changed:
            previous_seq = previous_ts = elapsed = None
            missed = 0
            reason = 'first_frame'
        else:
            if seq <= prev[1]:
                raise ValueError('source sequence must increase')
            previous_seq, previous_ts = prev[1], prev[2]
            elapsed, missed = ts-previous_ts, seq-previous_seq-1
            reason = 'sequence_gap' if missed else 'timestamp_gap' if elapsed > PAIR_NS else 'ok'
        if (stats['source_previous_sequence'] != previous_seq or stats['pair_elapsed_ns'] != elapsed
            or stats['missed_frames'] != missed or stats['reason'] != reason
            or stats['difference_valid'] != (reason == 'ok')):
            raise ValueError('inconsistent PL source/pair identity')
        for name in ('source_previous_sequence', 'pair_elapsed_ns'):
            if stats[name] is not None:
                integer(stats[name], name)
        integer(stats['missed_frames'], 'missed_frames')
        if stats['difference_valid']:
            maximum = integer(stats['diff_max'], 'diff_max', high=255)
            total = integer(stats['diff_sum'], 'diff_sum', high=19200*maximum)
            score = total/19200
        else:
            if stats['diff_sum'] is not None or stats['diff_max'] is not None:
                raise ValueError('invalid pair contains difference values')
            score = None
        self.previous = (ep, seq, ts)
        if changed:
            reason = 'epoch_changed'
        if now_ns-ts > PAIR_NS:
            reason = 'stale'
        valid = reason == 'ok'
        return dict(epoch=ep, source_sequence=seq, timestamp_ns=ts,
            source_previous_sequence=previous_seq, previous_timestamp_ns=previous_ts,
            pair_elapsed_ns=elapsed, roi=list(ROI), pixel_count=19200,
            valid=valid, reason=reason, score=score if valid else None)


def phase_at(elapsed_ns):
    integer(elapsed_ns, 'elapsed_ns', high=60_000_000_000-1)
    index = elapsed_ns//20_000_000_000
    return LABELS[index], math.ceil(((index+1)*20_000_000_000-elapsed_ns)/1e9)


class Calibration:
    def __init__(self):
        self.phase = None
        self.window = deque(maxlen=3)

    def update(self, row, *, elapsed_ns):
        phase, remaining = phase_at(elapsed_ns)
        stable = elapsed_ns%20_000_000_000 >= 2_000_000_000
        if phase != self.phase or not row['valid'] or not stable:
            self.window.clear()
        self.phase = phase
        if row['valid'] and stable:
            self.window.append(score_value(row['score']))
        smoothed = median(self.window) if len(self.window) == 3 else None
        return dict(row, phase_label=phase, phase_remaining_seconds=remaining,
            smoothed_score=smoothed, prediction='UNKNOWN', candidate=None, candidate_count=0,
            threshold_identity=None, prediction_reason='uncalibrated',
            calibration_sample=bool(smoothed is not None and stable))


def nearest_rank(values, fraction):
    if not values or not 0 < fraction <= 1:
        raise ValueError('nonempty nearest-rank quantile required')
    return sorted(values)[math.ceil(len(values)*fraction)-1]


def gates(medians):
    s, l, h = medians
    return [(s+l)/2, (l+h)/2], [s+(l-s)/3, s+2*(l-s)/3, l+(h-l)/3, l+2*(h-l)/3]


def fit_profile(rows, log_sha256):
    if len(rows) > 300:
        raise ValueError('calibration exceeds finite 300-frame scope')
    groups = {label: [] for label in LABELS}
    for row in rows:
        if row.get('calibration_sample') is True:
            groups[row['phase_label']].append(score_value(row['smoothed_score']))
    if any(len(v) < 30 for v in groups.values()):
        raise ValueError('insufficient calibration: need 30 stable smoothed scores per class')
    classes = {label: dict(count=len(v), median=median(v), p10=nearest_rank(v, .1),
                          p90=nearest_rank(v, .9)) for label, v in groups.items()}
    medians = [classes[label]['median'] for label in LABELS]
    initial, hysteresis = gates(medians)
    profile = dict(schema=SCHEMA, calibration_log_sha256=log_sha256, roi=list(ROI),
        target_fps=5, pair_max_ns=PAIR_NS, median_window=3, confirmation_updates=2,
        classes=classes, initial=initial, hysteresis=hysteresis,
        distributions_overlap=any(classes[a]['p90'] >= classes[b]['p10'] for a,b in zip(LABELS, LABELS[1:])),
        independent_validation_passed=False, labels_scope='instructed protocol, not verified human ground truth')
    validate_profile(profile)
    return profile


def validate_profile(p):
    try:
        if (p['schema'] != SCHEMA or p['roi'] != ROI or p['target_fps'] != 5
            or p['pair_max_ns'] != PAIR_NS or p['median_window'] != 3 or p['confirmation_updates'] != 2
            or len(p['calibration_log_sha256']) != 64
            or any(c not in '0123456789abcdef' for c in p['calibration_log_sha256'])
            or set(p['classes']) != set(LABELS)):
            raise ValueError('motion profile contract changed')
        medians = []
        for label in LABELS:
            d = p['classes'][label]
            integer(d['count'], 'class sample count', 30, 300)
            medians.append(score_value(d['median']))
            if not score_value(d['p10']) <= d['median'] <= score_value(d['p90']):
                raise ValueError('profile distribution inconsistent')
        if not medians[0] < medians[1] < medians[2]:
            raise ValueError('class medians not strictly ordered; no runnable profile')
        if (p['initial'], p['hysteresis']) != gates(medians):
            raise ValueError('motion gates differ from calibrated medians')
        return p
    except (KeyError, TypeError) as exc:
        raise ValueError('malformed motion profile') from exc


class Classifier:
    def __init__(self, profile):
        self.profile = validate_profile(json.loads(json.dumps(profile, allow_nan=False))) if profile is not None else None
        self.identity = None if profile is None else hashlib.sha256(
            json.dumps(profile, sort_keys=True, allow_nan=False).encode()).hexdigest()
        self.window = deque(maxlen=3)
        self.prediction = 'UNKNOWN'
        self.candidate = None
        self.count = 0
        self.timestamp_ns = None
        self.reason = 'uninitialized'

    def _reset(self, reason):
        self.window.clear()
        self.prediction, self.candidate, self.count, self.reason = 'UNKNOWN', None, 0, reason

    def current(self, *, now_ns):
        if self.timestamp_ns is not None and integer(now_ns, 'now_ns', self.timestamp_ns)-self.timestamp_ns > PAIR_NS:
            self._reset('stale')
        return dict(prediction=self.prediction, candidate=self.candidate, candidate_count=self.count,
            smoothed_score=median(self.window) if len(self.window) == 3 else None,
            threshold_identity=self.identity, reason=self.reason)

    def update(self, row, *, now_ns):
        self.timestamp_ns = integer(row['timestamp_ns'], 'timestamp_ns')
        if not row['valid'] or integer(now_ns, 'now_ns', self.timestamp_ns)-self.timestamp_ns > PAIR_NS:
            self._reset(row['reason'] if not row['valid'] else 'stale')
        else:
            self.window.append(score_value(row['score']))
            self.reason = 'uncalibrated' if self.profile is None else 'warming'
            if self.profile is not None and len(self.window) == 3:
                value = median(self.window)
                lo, hi = self.profile['initial']
                down1, up1, down2, up2 = self.profile['hysteresis']
                if self.prediction == 'UNKNOWN':
                    wanted = 'STATIC' if value < lo else 'LIGHT' if value < hi else 'HEAVY'
                elif self.prediction == 'STATIC':
                    wanted = 'HEAVY' if value >= up2 else 'LIGHT' if value >= up1 else 'STATIC'
                elif self.prediction == 'HEAVY':
                    wanted = 'STATIC' if value <= down1 else 'LIGHT' if value <= down2 else 'HEAVY'
                else:
                    wanted = 'STATIC' if value <= down1 else 'HEAVY' if value >= up2 else 'LIGHT'
                self.reason = 'ok'
                if wanted == self.prediction:
                    self.candidate, self.count = None, 0
                else:
                    self.count = self.count+1 if wanted == self.candidate else 1
                    self.candidate = wanted
                    if self.count >= 2:
                        self.prediction, self.candidate, self.count = wanted, None, 0
        return self.current(now_ns=now_ns)
