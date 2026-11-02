"""One owner-process GC window, bounded by the frozen session lifecycle."""
import gc
from pathlib import Path
import time


def memory_snapshot(path='/proc/self/status'):
    result = dict(available=False, rss_kib=None, process_lifetime_peak_kib=None,
                  source='proc_self_status', error='', at_ns=time.monotonic_ns())
    try:
        values = {}
        for line in Path(path).read_text(encoding='ascii').splitlines():
            if line.startswith(('VmRSS:', 'VmHWM:')):
                key, amount, unit = line.split()
                if unit != 'kB': raise ValueError('unexpected memory unit')
                values[key] = int(amount)
        if values.get('VmRSS:', 0) <= 0 or values.get('VmHWM:', 0) < values['VmRSS:']:
            raise ValueError('missing or invalid RSS/HWM')
        result.update(available=True, rss_kib=values['VmRSS:'],
                      process_lifetime_peak_kib=values['VmHWM:'])
    except (OSError, ValueError, KeyError) as exc:
        result['error'] = str(exc)
    return result


class Window:
    def __init__(self):
        self.started_ns = self.ended_ns = 0
        self.original_enabled = self.final_enabled = None
        self.thresholds_before = self.thresholds_after = None
        self.collections_before = self.collections_after = None
        self.memory_before = self.memory_at_restore = None
        self.restore_reason = ''
        self.errors = []

    def enter(self):
        if self.started_ns:
            raise RuntimeError('GC对照窗口只能进入一次')
        self.memory_before = memory_snapshot()
        if not self.memory_before['available']:
            raise RuntimeError('无法读取所有者内存，拒绝启动GC暂缓对照')
        self.original_enabled = gc.isenabled()
        self.thresholds_before = gc.get_threshold()
        gc.disable()
        self.started_ns = time.monotonic_ns()
        self.collections_before = [s['collections'] for s in gc.get_stats()]

    def restore(self, reason):
        if not self.started_ns or self.ended_ns:
            return
        try:
            self.collections_after = [s['collections'] for s in gc.get_stats()]
            self.memory_at_restore = memory_snapshot()
            if gc.isenabled():
                self.errors.append('窗口结束前自动GC已意外开启')
        except BaseException as exc:
            # Measurement failure must not prevent GC restoration or hardware cleanup.
            self.errors.append(type(exc).__name__+': '+str(exc))
        finally:
            self.ended_ns = time.monotonic_ns()
            self.restore_reason = reason
            (gc.enable if self.original_enabled else gc.disable)()
            self.final_enabled = gc.isenabled()
            self.thresholds_after = gc.get_threshold()

    def report(self):
        delta = None
        if self.collections_before is not None and self.collections_after is not None:
            delta = [b-a for a, b in zip(self.collections_before, self.collections_after)]
        restored = bool(self.ended_ns and self.original_enabled == self.final_enabled
                        and self.thresholds_before == self.thresholds_after)
        before, after = self.memory_before or {}, self.memory_at_restore or {}
        return dict(started_ns=self.started_ns, ended_ns=self.ended_ns,
            window_seconds=(self.ended_ns-self.started_ns)/1e9 if self.ended_ns else None,
            original_enabled=self.original_enabled, final_enabled=self.final_enabled,
            thresholds_before=self.thresholds_before, thresholds_after=self.thresholds_after,
            collections_before=self.collections_before, collections_after=self.collections_after,
            collections_delta=delta, restored=restored, restore_reason=self.restore_reason,
            memory_before=self.memory_before, memory_at_restore=self.memory_at_restore,
            rss_change_kib=after['rss_kib']-before['rss_kib']
                if before.get('available') and after.get('available') else None,
            errors=list(self.errors))


def install_session(session, window):
    if session.settings.duration_seconds != 60.:
        raise ValueError('GC对照仅允许原60秒单次静止配置')
    source = session.source
    original_begin, original_finish = source.begin, session._finish
    def begin():
        # Called by producer AFTER frozen PS warmup and thread readiness.
        window.enter()
        return original_begin()
    def finish(*args, **kwargs):
        # Original stop() only enters _finish once all capture/processing/writer threads exit.
        window.restore('threads_drained_before_finalization')
        return original_finish(*args, **kwargs)
    def undo():
        source.begin = original_begin
        session._finish = original_finish
    try:
        source.begin = begin
        session._finish = finish
    except BaseException:
        undo()
        raise
    return undo
