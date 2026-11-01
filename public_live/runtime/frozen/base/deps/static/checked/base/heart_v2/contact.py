from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ContactState:
    recorded_contact_ok: bool | None
    derived_contact_ok: bool
    disagrees_with_recorded: bool
    update_allowed: bool
    trusted_allowed: bool
    reason: str


class ContactGate:
    def __init__(
        self,
        low_ir_threshold,
        baseline_alpha,
        baseline_jump_fraction,
        amplitude_window_samples,
        minimum_pulse_amplitude,
        recovery_samples,
    ):
        self.low_ir_threshold = float(low_ir_threshold)
        self.baseline_alpha = float(baseline_alpha)
        self.baseline_jump_fraction = float(baseline_jump_fraction)
        self.amplitude_window_samples = int(amplitude_window_samples)
        self.minimum_pulse_amplitude = float(minimum_pulse_amplitude)
        self.recovery_samples = int(recovery_samples)
        self.reset()

    def reset(self):
        self.baseline = None
        self.window = deque(maxlen=self.amplitude_window_samples)
        self.recovered = 0
        self.pending_baseline = None
        self.pending_count = 0

    def _clear_signal_history(self):
        self.window.clear()
        self.recovered = 0

    def _track_rebaseline_candidate(self, value):
        if self.pending_baseline is None or abs(value - self.pending_baseline) > (
            self.baseline_jump_fraction * max(abs(self.pending_baseline), 1.0)
        ):
            self.pending_baseline = value
            self.pending_count = 1
        else:
            self.pending_count += 1
            self.pending_baseline += (
                value - self.pending_baseline
            ) / self.pending_count

        if self.pending_count >= self.recovery_samples:
            self.baseline = self.pending_baseline
            self.pending_baseline = None
            self.pending_count = 0

    def step(self, ir_raw, recorded_contact_ok=None):
        value = float(ir_raw)
        recorded = None if recorded_contact_ok is None else bool(recorded_contact_ok)
        reason = "ok"
        derived = True
        if value < self.low_ir_threshold:
            derived, reason = False, "low_ir"
            self.pending_baseline = None
            self.pending_count = 0
        elif self.baseline is None:
            self.baseline = value
        elif abs(value - self.baseline) > self.baseline_jump_fraction * max(
            abs(self.baseline), 1.0
        ):
            derived, reason = False, "baseline_jump"
            self._track_rebaseline_candidate(value)
        else:
            self.pending_baseline = None
            self.pending_count = 0
            self.baseline += self.baseline_alpha * (value - self.baseline)

        if derived:
            self.window.append(value)
        else:
            self._clear_signal_history()
        amplitude_ok = (
            len(self.window) == self.amplitude_window_samples
            and max(self.window) - min(self.window) >= self.minimum_pulse_amplitude
        )
        self.recovered = self.recovered + 1 if derived and amplitude_ok else 0
        trusted = self.recovered >= self.recovery_samples
        disagreement = recorded is not None and recorded != derived
        return ContactState(recorded, derived, disagreement, derived, trusted, reason)
