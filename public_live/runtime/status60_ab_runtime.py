"""Cold spawn targets; algorithms are loaded only at the original owner prepare."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import ExitStack, contextmanager
from collections.abc import Mapping
from dataclasses import asdict
from functools import partial
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
if __package__:
    from .status60_ab_manifest import verify_ab_package, validate_epoch, POLICY
else:
    from status60_ab_manifest import verify_ab_package, validate_epoch, POLICY

@contextmanager
def replaced(module, name, value):
    old = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, old)

def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)

def process_stopped(process):
    if process is None or getattr(process, '_closed', False):
        return True
    return not process.is_alive()

def fault_record(fault):
    if fault is None:
        return None

    def plain_value(value):
        if isinstance(value, Mapping):
            return {k: plain_value(v) for k, v in value.items()}
        if isinstance(value, (tuple, list)):
            return [plain_value(v) for v in value]
        return value
    return dict(stage=fault.stage, reason=fault.reason, sequence=fault.sequence, occurred_ns=fault.occurred_ns, details=plain_value(fault.details))

def verify_module_root(module, root):
    if not Path(module.__file__).resolve().is_relative_to(Path(root).resolve()):
        raise ValueError('AB mixed dependency module: ' + module.__name__)

def summary_metadata(session):
    cap = getattr(getattr(session, 'source', None), 'source', None)
    context = getattr(cap, '_context', None)
    result = dict(candidate=True, context=asdict(context) if context is not None else None, pairing_scope='bounded_causal_historical_imu_read_reuse', raw_safety_clock_scope='observed_record_grid_with_fifo_host_evidence', frontend_clock_scope='observed_record_grid_with_fifo_host_evidence', display_time_scope='host_observation_time_unchanged', model_time_is_hardware_timestamp=False)
    if context is not None:
        pairs = cap.pairing_audit
        result.update(imu_read_count=len(cap.imu_reads), paired_record_count=sum((r['paired'] for r in pairs)), extra_imu_reuses=sum((r['reused'] for r in pairs)), max_pair_age_ns=max((r['age_ns'] for r in pairs if r['age_ns'] is not None), default=None))
    return result

class Activation:

    def __init__(self, root, directory, expected_sha, epoch, stack):
        self.root, self.directory = (Path(root).resolve(), Path(directory))
        self.expected_sha, self.epoch, self.stack = (expected_sha, epoch, stack)
        self.patch = self.session = self.binding = None
        self.prepares = 0
        self.installed = False
        self.error = None
        self.events = []

    def install(self):
        if self.installed:
            raise RuntimeError('AB prepare can occur only once')
        import status60_ab_patch as patch
        verify_module_root(patch, self.root)
        self.patch = patch
        if (patch.PAIR_POLICY, patch.CLOCK_POLICY, patch.AGE_NS, patch.ERROR_NS, patch.HOST_LIMIT_NS, patch.PERIOD_NS, patch.WINDOW_NS, patch.ANCHORS, patch.AUDIT_CAPACITY) != (POLICY['pairing_policy_version'], POLICY['clock_policy_version'], POLICY['pair_age_ns'], POLICY['count_error_ns'], POLICY['host_limit_ns'], POLICY['period_ns'], POLICY['window_ns'], POLICY['anchors'], POLICY['audit_capacity']):
            raise ValueError('actual AB constants differ')
        self.stack.enter_context(patch.install_patches())
        from effective25.session import Session25
        original = Session25._make_summary

        def make_summary(session, *args, **kwargs):
            value = original(session, *args, **kwargs)
            value['a3c'] = summary_metadata(session)
            return value
        self.stack.enter_context(replaced(Session25, '_make_summary', make_summary))
        self.installed = True
        self.events.append('classes_installed_after_bootstrap')

    def bind(self, session):
        self.session = session
        self.prepares += 1
        if self.prepares != 1:
            raise RuntimeError('AB session bound twice')
        m = self.patch
        source = session.source
        cap = source.source
        if not (isinstance(source, m.EvidenceSource25) and isinstance(cap, m.BatchPairCapture25) and isinstance(session._frontend, m.SampleClockFrontend25) and isinstance(session._safety, m.SampleClockSafety25)):
            raise ValueError('actual joint session candidate types differ')
        from effective25.policy import validate_registers
        p = session._preflight
        validate_registers(p['sensor_registers'])
        if (p['adc_hz'], p['raw_hz'], p['processing_hz'], p['fifo_sample_average']) != (50, 25, 25, 2):
            raise ValueError('actual joint sensor rate differs')
        if (p['bit_sha256'], p['hwh_sha256']) != ('6dc798a77f8577629f5d824bf9081e994352b4cd104dde31b8b265c621bdd966', '3c44a48758fce3f1a581f8ae3d74d543a712b539d922fad8c739b4bd7a5b9393'):
            raise ValueError('actual integrated bit/HWH differs')
        identity = dict(schema='a3c_sensor_config_v1', manifest_sha256=self.expected_sha, pairing_policy_version=m.PAIR_POLICY, clock_policy_version=m.CLOCK_POLICY, sensor_registers=p['sensor_registers'], adc_hz=p['adc_hz'], raw_hz=p['raw_hz'], processing_hz=p['processing_hz'], fifo_sample_average=p['fifo_sample_average'], bit_sha256=p['bit_sha256'], hwh_sha256=p['hwh_sha256'])
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        context = m.AcquisitionContext25(self.epoch, self.expected_sha, digest, m.PAIR_POLICY, m.CLOCK_POLICY)
        begin = source.begin
        stop = session.stop
        snapshot = session.snapshot
        cap.bind_context(context)
        session._safety.bind_context(context)
        session._frontend.bind_context(context)
        if source is not session.source or source.begin != begin or session.stop != stop or (session.snapshot != snapshot):
            raise ValueError('original joint lifecycle wrappers changed')
        p.update(a3c=summary_metadata(session), run_epoch=self.epoch, config_identity_sha256=digest, pairing_scope='bounded_causal_historical_imu_read_reuse')
        self.events.append('existing_joint_session_bound_before_start')

    def export(self):
        session = self.session
        if session is not None:
            if any((t.is_alive() for t in getattr(session, '_threads', ()))):
                raise RuntimeError('AB export blocked: heart writer active')
            finalizer = getattr(session, '_finalizer', None)
            if finalizer is not None and finalizer.is_alive():
                raise RuntimeError('AB finalizer active')
            if not process_stopped(getattr(getattr(session, '_process_chain', None), '_worker', None)):
                raise RuntimeError('AB PS child still active')
        if self.binding is not None:
            from joint_concurrent_worker import retention_reasons
            if retention_reasons(self.binding):
                raise RuntimeError('AB original resources retained')
        directory = self.directory / 'a3c'
        directory.mkdir(parents=True, exist_ok=False)
        tables = {}
        context = None
        overflows = {}
        if session is not None and self.patch is not None:
            cap = session.source.source
            context = getattr(cap, '_context', None)
            if isinstance(cap, self.patch.BatchPairCapture25):
                tables['pairing.jsonl'] = cap.pairing_audit
                tables['imu-reads.jsonl'] = cap.imu_reads
                overflows['pairing'] = cap.pairing_audit.overflow
                overflows['imu'] = cap.imu_reads.overflow
            continuity = []
            for side, state in [('raw', session._safety._supervisor), ('processing', session._frontend.supervisor)]:
                if isinstance(state, self.patch.ClockedSupervisor25):
                    continuity.extend((dict(row, side=side) for row in state.tracker.audit))
                    overflows[side] = state.tracker.audit.overflow
            tables['continuity-evidence.jsonl'] = continuity
        index = {}
        for name, rows in tables.items():
            path = directory / name
            with path.open('x', encoding='utf-8') as stream:
                for row in rows:
                    stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            index[name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), rows=len(rows))
        original_fault = getattr(session, '_fault', None) if session is not None else None
        activation = dict(schema='a3c_actual_joint_activation_v1', events=self.events, error=self.error, prepares=self.prepares, installed=self.installed, context=asdict(context) if context else None, runtime_path='main_spatial_owner_sample_v1', ps_wrapper='status60_ab_runtime.verified_ps_worker', original_fault=fault_record(original_fault), original_base_preserved=True, hardware_acceptance_passed=False)
        public_identity = getattr(self, 'public_release_identity', None)
        if public_identity is not None:
            activation.update(schema='trusted_heart_public_a3c_activation_v1',
                public_release_identity=public_identity,
                original_base_preserved=False,
                historical_numerical_qualification=False)
        write_new(directory / 'activation.json', activation)
        raw = self.directory / 'capture/raw.csv'
        write_new(directory / 'audit-index.json', dict(files=index, audit_capacity=POLICY['audit_capacity'], overflows=overflows, input_raw_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.is_file() else None, context=asdict(context) if context else None, original_error=self.error))

def verified_ps_worker(connection, backend_source, *, root, source, run_id, expected_manifest_sha256, run_epoch, host_check=False, release_contract=None):
    if release_contract is not None:
        expected_manifest_sha256 = release_contract['expected_manifest_sha256']
    verify_ab_package(root, expected_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    validate_epoch(run_epoch)
    import main_spatial_ps
    verify_module_root(main_spatial_ps, root)
    return main_spatial_ps.ps_worker(connection, backend_source, root=root, source=source, run_id=run_id, host_check=host_check, release_contract=release_contract)

def ab_owner_worker(*args, root, expected_manifest_sha256, run_epoch, release_contract=None, **kwargs):
    if release_contract is not None:
        expected_manifest_sha256 = release_contract['expected_manifest_sha256']
    verify_ab_package(root, expected_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    validate_epoch(run_epoch)
    import status60_runtime, joint_concurrent_owner, main_spatial_ps
    for module in [status60_runtime, joint_concurrent_owner, main_spatial_ps]:
        verify_module_root(module, root)
    original_main = joint_concurrent_owner.owner_main
    with ExitStack() as stack:
        registry = Activation(root, args[1], expected_manifest_sha256, run_epoch, stack)
        if release_contract is not None:
            registry.public_release_identity = verify_boundary(root, release_contract)

        def candidate_main(binding, owner_root, directory, mailbox, stop, metrics_ready, *, dependencies=None, **options):
            registry.binding = binding
            deps = dependencies or joint_concurrent_owner._dependencies()
            previous_prepare = deps.prepare

            def prepare(*a, **kw):
                registry.install()
                session = previous_prepare(*a, **kw)
                try:
                    registry.bind(session)
                except BaseException as exc:
                    registry.session = session
                    registry.error = dict(stage='a3c_prepare', type=type(exc).__name__, message=str(exc))
                    session._fail('a3c_prepare', str(exc))
                    stop.set()
                return session
            actual = SimpleNamespace(**vars(deps))
            actual.prepare = prepare
            return original_main(binding, owner_root, directory, mailbox, stop, metrics_ready, dependencies=actual, **options)
        worker = partial(verified_ps_worker, expected_manifest_sha256=expected_manifest_sha256, run_epoch=run_epoch, release_contract=release_contract)
        stack.enter_context(replaced(main_spatial_ps, 'ps_worker', worker))
        stack.enter_context(replaced(joint_concurrent_owner, 'owner_main', candidate_main))
        failure = None
        try:
            return status60_runtime.owner_worker(*args, root=root, **kwargs, release_contract=release_contract)
        except BaseException as exc:
            failure = exc
            registry.error = registry.error or dict(type=type(exc).__name__, message=str(exc))
            raise
        finally:
            try:
                registry.export()
            except BaseException as export_error:
                if failure is not None:
                    raise failure from export_error
                raise

def ab_start_owner(context, *args, root, expected_manifest_sha256, run_epoch, release_contract=None, **kwargs):
    if release_contract is not None:
        expected_manifest_sha256 = release_contract['expected_manifest_sha256']
    if Path(root).resolve() != Path(__file__).resolve().parent:
        raise ValueError('AB owner root differs')
    verify_ab_package(root, expected_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    validate_epoch(run_epoch)
    child = context.Process(target=partial(ab_owner_worker, root=root, expected_manifest_sha256=expected_manifest_sha256, run_epoch=run_epoch, **kwargs, release_contract=release_contract), args=args, name='joint25-a3r-ce-main-owner', daemon=False)
    child.start()
    return child
