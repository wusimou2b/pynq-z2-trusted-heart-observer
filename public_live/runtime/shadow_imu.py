"""Bounded read-only tap of existing processed motion; no sensor or IPC access."""
from collections import deque
import math
import threading

if __package__:
    from .roi_motion_core import integer
else:
    from roi_motion_core import integer

PAIR_NS = 250_000_000


def evidence(record, observed_ns):
    integer(observed_ns, 'observed_ns')
    raw = record.saved.record.raw
    frame = record.runtime.frame
    sequence = integer(raw['sequence'], 'IMU sequence')
    if frame.sequence != sequence:
        raise ValueError('IMU processed/source sequence differs')
    epoch = record.runtime.pl_epoch
    if epoch is not None:
        integer(epoch, 'IMU epoch', high=0xffffffff)
    for name, value in (('pair_ok', raw['pair_ok']), ('accel_valid', raw['accel_valid']),
                        ('frame.valid', frame.valid), ('motion_ready', frame.motion_ready)):
        if type(value) is not bool:
            raise ValueError('invalid IMU bool: '+name)
    source = raw['mpu_read_completed_ns']
    if source in ('', None) and not raw['pair_ok']:
        source = None
    else:
        integer(source, 'mpu_read_completed_ns')
    finished = integer(record.processing_finished_ns, 'processing_finished_ns')
    if finished > observed_ns or source is not None and source > finished:
        raise ValueError('IMU availability precedes source/processing')
    label = frame.motion
    if label is not None and label not in ('static', 'light', 'heavy'):
        raise ValueError('invalid original IMU label')
    rms = frame.motion_rms_g
    if rms is not None and (type(rms) not in (int, float) or not math.isfinite(rms) or rms < 0):
        raise ValueError('invalid original IMU RMS')
    reason = ('missing_epoch' if epoch is None else 'unpaired' if not raw['pair_ok'] or not raw['accel_valid']
              else 'frame_invalid' if not frame.valid else 'motion_not_ready'
              if not frame.motion_ready or label is None or rms is None else 'ok')
    return dict(sequence=sequence, epoch=epoch, source_ns=source, processing_finished_ns=finished,
                observed_ns=observed_ns, label=label.upper() if reason == 'ok' else 'UNKNOWN',
                rms_g=rms, valid=reason == 'ok', reason=reason)


class ImuBuffer:
    def __init__(self):
        self._records = deque(maxlen=64)
        self._lock = threading.Lock()
        self._last = None
        self._generation = self._observations = self._duplicates = self._resets = 0

    def observe(self, record, *, observed_ns):
        if record is None:
            integer(observed_ns, 'observed_ns')
            return False
        row = evidence(record, observed_ns)
        with self._lock:
            previous = self._last
            if previous is not None:
                if row['observed_ns'] < previous['observed_ns']:
                    raise ValueError('IMU observation clock rollback')
                if (row['epoch'], row['sequence']) == (previous['epoch'], previous['sequence']):
                    if any(v != previous[k] for k, v in row.items() if k != 'observed_ns'):
                        raise ValueError('IMU duplicate identity payload changed')
                    self._duplicates += 1
                    return False
                if row['epoch'] != previous['epoch']:
                    self._records.clear()
                    self._generation += 1
                    self._resets += 1
                elif row['sequence'] <= previous['sequence']:
                    raise ValueError('IMU processed sequence rollback')
            # Missing source is a barrier, never permission to select an older valid row.
            if row['source_ns'] is None:
                self._records.clear()
            self._records.append(row)
            self._last = row
            self._observations += 1
            return True

    def invalidate_pairing(self):
        """A video reset invalidates old evidence without re-admitting duplicates."""
        with self._lock:
            self._records.clear()
            self._generation += 1

    def match(self, video_ns, now_ns):
        integer(video_ns, 'video_ns')
        integer(now_ns, 'now_ns', video_ns)
        with self._lock:
            rows = [dict(r) for r in self._records if r['observed_ns'] <= now_ns]
            generation = self._generation
        current = rows[-1] if rows else None
        def fresh(row):
            return bool(row and row['valid'] and row['source_ns'] is not None
                        and 0 <= now_ns-row['source_ns'] <= PAIR_NS)
        past = [r for r in rows if r['source_ns'] is not None and r['source_ns'] <= video_ns]
        candidate = past[-1] if past else None
        age = None if candidate is None else now_ns-candidate['source_ns']
        delta = None if candidate is None else video_ns-candidate['source_ns']
        reason = ('no_past_source' if candidate is None else candidate['reason'] if not candidate['valid']
                  else 'imu_stale' if age > PAIR_NS else 'unmatched' if delta > PAIR_NS else 'ok')
        paired = reason == 'ok'
        return dict(candidate=candidate, current=current, current_available=fresh(current), pair_available=paired,
                    label=candidate['label'] if paired else 'UNKNOWN', reason=reason, age_ns=age, delta_ns=delta,
                    generation=generation)

    def report(self):
        with self._lock:
            return dict(capacity=64, stored=len(self._records), observations=self._observations,
                        duplicates=self._duplicates, epoch_resets=self._resets, generation=self._generation)
