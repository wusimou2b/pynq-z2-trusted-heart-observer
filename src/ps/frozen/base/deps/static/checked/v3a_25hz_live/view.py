"""Refresh against a fresh session snapshot before AND after rendering."""
from collections import deque
import time

from heart_v3a.live.view import presentation


def presentation25(snapshot, now_ns):
    value = presentation(snapshot, now_ns=now_ns)
    safety = snapshot.counts.get('raw_safety')
    if safety is not None:
        value['contact_cn'] = '正常' if safety['contact_ready'] else '异常／恢复中'
    if snapshot.latest and snapshot.latest.runtime.frame.selected_route == 'mean':
        value['route_cn'] = '两点均值（25Hz）'
    return value


def generation(snapshot):
    return snapshot.counts.get('raw_safety', {}).get('generation')


class LiveView25:
    """Renderer injection keeps this logic testable without a browser or hardware.

    A caller must keep refreshing. This is not a browser-side heartbeat watchdog.
    A rendered number cannot be revoked while the caller/browser is suspended.
    """
    def __init__(self, snapshot_provider, render, *, clock=time):
        self.provider, self.render, self.clock = snapshot_provider, render, clock
        self._last_refresh = None
        self._last_value = None
        self._samples = deque(maxlen=500)
        self._refreshes = self._errors = 0
        self._disabled = False
        self._error = ''

    def refresh(self):
        if self._disabled:
            return False
        try:
            now = self.clock.monotonic_ns()
            snapshot = self.provider()
            value = presentation25(snapshot, now)
            revoke = (self._last_value is not None and self._last_value['bpm_text'] != 'N/A'
                      and value['bpm_text'] == 'N/A')
            if self._last_refresh is not None and now-self._last_refresh < 500_000_000 and not revoke:
                return False
            self._last_refresh = now
            self.render(snapshot, value)
            finished = self.clock.monotonic_ns()
            fresh = self.provider()
            checked = presentation25(fresh, finished)
            if value['bpm_text'] != 'N/A' and (checked['bpm_text'] == 'N/A' or generation(fresh) != generation(snapshot)):
                checked.update(bpm_text='N/A', reason_cn='渲染期间原始安全许可／新鲜度变化，撤销旧BPM')
                self.render(fresh, checked)
                snapshot, value = fresh, checked
                finished = self.clock.monotonic_ns()
            self._last_value = value
            self._refreshes += 1
            if snapshot.latest is not None:
                latest = snapshot.latest
                read_ns = latest.saved.record.read_completed_ns
                self._samples.append(dict(sequence=latest.runtime.frame.sequence,
                    read_completed_ns=read_ns, refresh_completed_ns=finished,
                    read_to_display_ns=finished-read_ns, render_ns=finished-now,
                    bpm_text=value['bpm_text'], historical=value['historical']))
            return True
        except Exception as exc:
            self._errors += 1
            self._disabled, self._error = True, str(exc)
            return False

    def finish(self):
        try:
            snapshot = self.provider()
            value = presentation25(snapshot, self.clock.monotonic_ns())
            value.update(bpm_text='N/A', historical=True, reason_cn='查看结束，曲线仅供历史查看')
            self.render(snapshot, value)
            self._last_value = value
            self._disabled = True
            return True
        except Exception as exc:
            self._errors += 1
            self._disabled, self._error = True, str(exc)
            return False

    def metrics(self):
        return dict(refreshes=self._refreshes, display_errors=self._errors, disabled=self._disabled,
                    error=self._error, samples=[dict(row) for row in self._samples])
