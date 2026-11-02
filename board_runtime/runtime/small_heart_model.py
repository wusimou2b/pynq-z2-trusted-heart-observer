"""Software-only, ordered reference for the proposed heart candidate IP.

This is deliberately NOT an MMIO backend or evidence of FPGA acceleration.
The owner-side software NLMS and original floating point detectors remain
visible costs in software timings; they must not be called hardware timings.
"""
from collections import deque
from dataclasses import dataclass
import math

BRANCHES = ('raw', 'mean', 'nlms', 'joint')


@dataclass(frozen=True)
class Identity:
    run_id: str
    request_id: int
    sequence: int
    generation: int


@dataclass(frozen=True)
class PrepRequest:
    identity: Identity
    valid: bool
    reset: bool
    ir_raw: float | None
    references: tuple
    beta_int: int = 32212255


@dataclass(frozen=True)
class BankRequest:
    identity: Identity
    core_epoch: int
    joint: float
    contact_ready: bool


@dataclass(frozen=True)
class PrepResult:
    identity: Identity
    core_epoch: int
    raw: float | None
    mean: float | None
    reply: object


@dataclass(frozen=True)
class BranchResult:
    filtered: float
    peak: bool
    bpm: float | None
    ibis: tuple
    sample_index: int
    last_peak_index: int | None
    last_peak_position: float | None
    accepted_peak_count: int


@dataclass(frozen=True)
class BankResult:
    identity: Identity
    core_epoch: int
    branches: dict


def detector_state(detector):
    """Full migration state, read only for proof, never ordinary IPC."""
    keys = ('sample_index', 'last_peak_index', 'last_peak_position',
            'accepted_peak_count', 'previous', 'previous_previous',
            'previous_trusted', 'previous_previous_trusted', 'envelope',
            '_interval_key', '_bpm')
    return dict({k: getattr(detector, k) for k in keys},
                zi=detector.zi.tobytes().hex(), ibis=tuple(detector.ibis))


def _identity(identity):
    if (not isinstance(identity, Identity) or not isinstance(identity.run_id, str)
            or not 0 < len(identity.run_id) <= 128
            or any(type(v) is not int or v < 0 for v in
                   (identity.request_id, identity.sequence, identity.generation))
            or identity.request_id == 0):
        raise ValueError('invalid small-heart identity')


class Model:
    source = 'python_fixed'

    def __init__(self, config, sections, nlms):
        if nlms.source != 'python_fixed':
            raise ValueError('software model cannot authorize hardware')
        from heart_v2.preprocess import CausalDcBlocker
        from peak_timing import FractionalPeakDetector
        self.backend = nlms
        self._dc_type, self._detector_type = CausalDcBlocker, FractionalPeakDetector
        self.config, self.sections = config, tuple(tuple(s) for s in sections)
        self._controls = (32212255, True, False)
        self._reply = None
        self.epoch = self.core_epoch = 0
        self.fault = ''
        self.pending = None
        self.previous = None
        self.next_sequence = 0
        self.counts = dict(prep=0, nlms=0, bank=0)

    def _clear_signals(self):
        self.dc = self._dc_type(self.config['preprocess']['ppg_dc_alpha'])
        self.mean_window = deque(maxlen=2)
        self.detectors = {}
        for key in BRANCHES:
            detector = self._detector_type(25, **self.config['heartrate'])
            detector._sections = self.sections
            self.detectors[key] = detector

    def reset(self):
        if self.epoch or self.fault:
            raise RuntimeError('reset once; a locked run needs a new instance')
        self.epoch = self.backend.reset()
        self.core_epoch += 1
        self._clear_signals()
        return self.epoch

    def identity(self, sequence, generation):
        return Identity('direct-model', sequence+1, sequence, generation)

    def _ready(self):
        if self.fault:
            raise RuntimeError('small-heart model locked: '+self.fault)
        if not self.epoch:
            raise RuntimeError('small-heart model not initialized')

    def prep(self, request):
        self._ready()
        try:
            return self._prep(request)
        except BaseException as exc:
            self.fault = str(exc) or type(exc).__name__
            raise

    def _prep(self, request):
        import numpy as np
        from heart_v3a.runtime_pl_chain import RuntimePlMainChain
        if not isinstance(request, PrepRequest):
            raise ValueError('invalid PREP request type')
        _identity(request.identity)
        ident = request.identity
        if self.pending is not None or ident.sequence != self.next_sequence:
            raise ValueError('PREP repeated, missing BANK4, or sequence differs')
        if self.previous is not None and (ident.run_id != self.previous[0].run_id
                or ident.request_id <= self.previous[0].request_id):
            raise ValueError('PREP run/request identity differs')
        if (type(request.valid) is not bool or type(request.reset) is not bool
                or type(request.beta_int) is not int or request.beta_int != 32212255
                or not isinstance(request.references, tuple) or len(request.references) != 3
                or not all(math.isfinite(v) for v in request.references)):
            raise ValueError('PREP controls or references differ')
        reset = (not request.valid or self.previous is None
                 or ident.generation != self.previous[0].generation
                 or request.valid != self.previous[1])
        if request.reset != reset:
            raise ValueError('PREP reset does not match valid/generation transition')
        if reset:
            self._clear_signals()
        if request.valid:
            if request.ir_raw is None or not math.isfinite(request.ir_raw):
                raise ValueError('PREP IR must be finite')
            if reset:
                self.dc.reset(request.ir_raw)
            raw = self.dc.step(request.ir_raw)/self.config['preprocess']['ppg_scale_counts']
            staged = (*self.mean_window, raw)[-2:]
            mean = float(np.mean(staged))
        else:
            if request.ir_raw is not None or request.references != (0., 0., 0.):
                raise ValueError('invalid slot must use the original zero packet')
            raw = mean = None
        self.counts['prep'] += 1
        self.counts['nlms'] += 1
        reply = RuntimePlMainChain._send_packet(self, ident, raw or 0.,
            request.references, request.valid, request.valid, reset)
        if reply.epoch != self.epoch:
            raise ValueError('original NLMS epoch differs')
        result = PrepResult(ident, self.core_epoch, raw, mean, reply)
        if request.valid:
            self.pending = result
        else:
            self.previous = (ident, False)
            self.next_sequence += 1
        return result

    def bank(self, request):
        self._ready()
        try:
            return self._bank(request)
        except BaseException as exc:
            self.fault = str(exc) or type(exc).__name__
            raise

    def _bank(self, request):
        if (not isinstance(request, BankRequest) or self.pending is None
                or request.identity != self.pending.identity
                or type(request.core_epoch) is not int or request.core_epoch != self.core_epoch
                or type(request.contact_ready) is not bool or not math.isfinite(request.joint)
                or not self.pending.reply.status & 1):
            raise ValueError('BANK4 phase, identity, epoch or payload differs')
        prepared = self.pending
        values = dict(raw=prepared.raw, mean=prepared.mean,
                      nlms=prepared.reply.candidate_int/65536, joint=request.joint)
        result = {}
        for key, value in values.items():
            detector = self.detectors[key]
            state = detector.step(value, request.contact_ready)
            result[key] = BranchResult(state.filtered, state.peak, state.bpm,
                tuple(detector.ibis), detector.sample_index, detector.last_peak_index,
                detector.last_peak_position, detector.accepted_peak_count)
        self.mean_window.append(prepared.raw)
        self.previous = (request.identity, True)
        self.pending = None
        self.next_sequence += 1
        self.counts['bank'] += 1
        return BankResult(request.identity, self.core_epoch, result)

    def snapshot(self):
        self._ready()
        return dict(dc=(self.dc.previous_input, self.dc.previous_output),
                    mean_window=list(self.mean_window),
                    branches={k: detector_state(v) for k, v in self.detectors.items()})
