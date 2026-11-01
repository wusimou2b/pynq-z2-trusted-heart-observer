"""Software-only two-phase PS target with original imports and Native100."""
import gc
import json
import os
from pathlib import Path
import platform
import sys
import time

if __package__:
    from .small_heart_model import Identity, Model
    from .small_heart_chain import make_chain
else:
    from small_heart_model import Identity, Model
    from small_heart_chain import make_chain


def load_chain(root, prepared_source, *, host_check=False):
    if __package__:
        from .lean_ps_guard import verify_source
        from .lean_ps_worker import load_original
        from .statistics25_native import load_native, make_candidate
    else:
        from lean_ps_guard import verify_source
        from lean_ps_worker import load_original
        from statistics25_native import load_native, make_candidate
    prepared = verify_source(root, prepared_source, hardware=False, host_check=host_check)
    deps = load_original(Path(root)/'frozen')
    core = load_native(prepared['binary'])
    base = make_candidate(core).Chain
    from heart_v3a.runtime_backend import FixedNlmsBackend
    from entry25_guard import identity
    saved = json.loads((Path(root)/'frozen/provenance/entry25_board_check.json').read_text('utf-8'))
    sections = tuple(tuple(float.fromhex(v) for v in row) for row in saved['native_sos_hex'])
    arm = sys.platform == 'linux' and platform.machine() == 'armv7l'
    if arm:
        if base(FixedNlmsBackend()).output_detector._sections != sections:
            raise ValueError('original ARM SOS coefficients differ')
    elif host_check:
        original = base
        class HostChain(original):
            def _reset_signals(self):
                super()._reset_signals()
                for detector in (*self.detectors.values(), self.output_detector):
                    detector._sections = sections
        base = HostChain
    else:
        raise RuntimeError('host reproduction requires explicit host_check')
    config = base(FixedNlmsBackend()).config
    metadata = dict(identity(Path(root)/'frozen'), host_check=host_check, arm_native=arm,
        native_statistics=dict(loaded=True, implementation=core.implementation,
            binary_sha256=prepared['binary']['sha256'], c_sha256=prepared['c_sha256'],
            native_manifest_sha256=prepared['native_manifest_sha256'],
            preparation_sha256=prepared['preparation_sha256'], ps_pid=os.getpid()))
    return base, config, sections, metadata


class Remote:
    source = 'python_fixed'

    def __init__(self, connection, run_id):
        self.connection, self.run_id = connection, run_id
        self.request_id = self.epoch = 0

    def reset(self):
        return self.epoch

    def identity(self, sequence, generation):
        return Identity(self.run_id, self.request_id, sequence, generation)

    def _call(self, phase, request):
        self.connection.send((self.request_id, phase, request))
        if not self.connection.poll(1.):
            raise TimeoutError('small-heart owner reply missing; no retry')
        rid, kind, payload = self.connection.recv()
        if (rid, kind) != (self.request_id, phase+'_reply'):
            raise RuntimeError('small-heart reply phase/request differs')
        return payload

    def prep(self, request):
        return self._call('prep', request)

    def bank(self, request):
        return self._call('bank', request)


TRACE_COLUMNS = ('chain_wall_ns', 'chain_thread_ns', 'remote_wall_ns',
                 'remote_thread_ns', 'prep_roundtrip_ns', 'bank_roundtrip_ns')


def ps_worker(connection, source, *, root, prepared_source, host_check=False, run_id,
              placement='split', shared=None):
    rid = 0
    try:
        if source != 'python_fixed':
            raise ValueError('S1 worker cannot authorize hardware')
        if placement not in ('ps', 'split'):
            raise ValueError('unknown software placement')
        if __package__:
            from .lean_ps_worker import no_hardware
        else:
            from lean_ps_worker import no_hardware
        with no_hardware():
            base, config, sections, metadata = load_chain(root, prepared_source, host_check=host_check)
            from effective25.frontend import Frontend25
            from heart_v2.runtime_main_chain import Observation
            from heart_v3a.runtime_backend import FixedNlmsBackend
            import math
            chain_type = make_chain(base) if placement == 'split' else base
            warm = chain_type(Model(config, sections, FixedNlmsBackend())
                              if placement == 'split' else FixedNlmsBackend())
            front = Frontend25()
            for i in range(700):
                warm.step(front.push(Observation(i, i/25.,
                    125000.+600*math.sin(2*math.pi*1.2*i/25.), (0., 0., 1.), True)))
            del warm, front
            if placement == 'split':
                remote_type, remote_arg = Remote, run_id
            else:
                from heart_v3a.live.process_chain import _RemoteBackend
                remote_type, remote_arg = _RemoteBackend, source
            cost = dict.fromkeys(TRACE_COLUMNS, 0)
            if shared is not None:
                parent_type = remote_type
                class Observed(parent_type):
                    def _measure(self, fn, phase, *args):
                        w0, c0 = time.perf_counter_ns(), time.thread_time_ns()
                        try:
                            return fn(*args)
                        finally:
                            cost['remote_thread_ns'] += time.thread_time_ns()-c0
                            wall = time.perf_counter_ns()-w0
                            cost['remote_wall_ns'] += wall
                            cost[phase+'_roundtrip_ns'] += wall
                    def _call(self, phase, request):
                        return self._measure(super()._call, phase, phase, request)
                    def transact(self, packet):
                        return self._measure(super().transact, 'prep', packet)
                remote_type = Observed
            remote = remote_type(connection, remote_arg)
            chain = None
            connection.send((0, 'ready', dict(metadata, worker_pid=os.getpid(),
                warmup_slots=700, warmup_raw=700, ps_gc_enabled_at_ready=gc.isenabled(),
                worker_hardware_imported=False, small_heart_mode='software_reference_'+placement+'_v1')))
            while True:
                rid, kind, payload = connection.recv()
                remote.request_id = rid
                if kind == 'close':
                    return
                if kind == 'reset' and chain is None:
                    remote.epoch = payload
                    chain = chain_type(remote)
                    connection.send((rid, 'done', chain.epoch))
                elif kind == 'step' and chain is not None:
                    slot, controls = payload
                    if controls != dict(beta_int=32212255, update_enabled=True, bypass=False):
                        raise ValueError('original25 controls differ')
                    if shared is None:
                        result = chain.step(slot)
                    else:
                        if slot.sequence != shared['count'].value or slot.sequence >= 1504:
                            raise ValueError('bounded trace sequence differs')
                        cost.update(dict.fromkeys(TRACE_COLUMNS, 0))
                        w0, c0 = time.perf_counter_ns(), time.thread_time_ns()
                        result = chain.step(slot)
                        cost['chain_thread_ns'] = time.thread_time_ns()-c0
                        cost['chain_wall_ns'] = time.perf_counter_ns()-w0
                        offset = slot.sequence*len(TRACE_COLUMNS)
                        for i, key in enumerate(TRACE_COLUMNS):
                            shared['rows'][offset+i] = cost[key]
                        shared['count'].value += 1
                    connection.send((rid, 'done', result))
                else:
                    raise RuntimeError('invalid request or repeated initialization')
    except EOFError:
        return
    except BaseException as exc:
        try:
            connection.send((rid, 'error', type(exc).__name__+': '+str(exc)))
        except (OSError, EOFError):
            pass
    finally:
        connection.close()
