"""Frozen experimental video candidate; no heart controls, drivers or clocks."""
from collections import deque
import hashlib
import json
from statistics import median

if __package__:
    from .roi_motion_core import SourceAdapter, score_value
    from .spatial_features import checked_spatial, SPATIAL_FIELDS
else:
    from roi_motion_core import SourceAdapter, score_value
    from spatial_features import checked_spatial, SPATIAL_FIELDS

_PARAMETERS = json.dumps(dict(schema='v3b25_shadow_video_rule_v1', ratio_thresholds=[.15, .50],
    maximum_thresholds=[12., 75.], median_window=3, confirmation_updates=2,
    pixel_threshold=8, grid=[4, 3], roi=[80, 60, 240, 180], pair_max_ns=250_000_000,
    independent_validation_passed=False, heart_control_enabled=False), sort_keys=True, separators=(',', ':'))
_RULE_SHA = hashlib.sha256(_PARAMETERS.encode('utf-8')).hexdigest()


def profile():
    return dict(parameters=json.loads(_PARAMETERS), sha256=_RULE_SHA)


def ratio_band(value):
    score_value(value)
    if value > 1:
        raise ValueError('motion pixel ratio must be in 0..1')
    return 'STATIC' if value < .15 else 'HEAVY' if value >= .50 else 'LIGHT'


def maximum_band(value):
    score_value(value)
    return 'STATIC' if value < 12 else 'HEAVY' if value >= 75 else 'LIGHT'


class VideoCandidate:
    def __init__(self):
        self.source = SourceAdapter()
        self.window = deque(maxlen=3)
        self.candidate = None
        self.count = 0

    def clear(self):
        """Clear classification state without pretending physical frames reset."""
        self.window.clear()
        self.candidate = None
        self.count = 0

    def consume(self, stats, *, now_ns):
        spatial = checked_spatial(stats)
        source = self.source.consume(stats, now_ns=now_ns)
        fields = {name: None for name in SPATIAL_FIELDS}
        if source['valid']:
            fields.update({name: list(spatial[name]) if isinstance(spatial[name], list) else spatial[name]
                           for name in SPATIAL_FIELDS[:-1]})
            fields['max_block_mean_difference'] = max(spatial['block_mean_differences'])
        result = dict(source, **fields, label='UNKNOWN', prediction_reason=source['reason'],
            smoothed_motion_pixel_ratio=None, smoothed_max_block_mean_difference=None,
            ratio_candidate=None, maximum_candidate=None, candidate=None, candidate_count=0,
            rule_sha256=_RULE_SHA, freshness_checked_ns=now_ns, heart_control_enabled=False)
        if not source['valid']:
            self.clear()
        else:
            self.window.append(dict(source_sequence=source['source_sequence'], timestamp_ns=source['timestamp_ns'],
                motion_pixel_ratio=fields['motion_pixel_ratio'],
                max_block_mean_difference=fields['max_block_mean_difference']))
            if len(self.window) < 3:
                result['prediction_reason'] = 'window_warmup'
            else:
                ratio = median(v['motion_pixel_ratio'] for v in self.window)
                maximum = median(v['max_block_mean_difference'] for v in self.window)
                rb, mb = ratio_band(ratio), maximum_band(maximum)
                result.update(smoothed_motion_pixel_ratio=ratio, smoothed_max_block_mean_difference=maximum,
                              ratio_candidate=rb, maximum_candidate=mb)
                if rb != mb:
                    self.candidate, self.count = None, 0
                    result['prediction_reason'] = 'feature_disagreement'
                else:
                    self.count = min(2, self.count+1) if rb == self.candidate else 1
                    self.candidate = rb
                    result.update(label=rb if self.count >= 2 else 'UNKNOWN', candidate=rb,
                        candidate_count=self.count, prediction_reason='confirmed' if self.count >= 2 else 'pending')
        result['window'] = [dict(v) for v in self.window]
        return result
