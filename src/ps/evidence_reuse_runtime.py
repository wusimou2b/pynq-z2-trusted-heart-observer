"""Cold owner/PS targets: verify the candidate before downstream imports."""
from contextlib import ExitStack
from functools import partial
import hashlib
import json
from pathlib import Path
import time
from evidence_reuse_guard import verify


def verify_ps_prefix(root,expected_reuse_manifest_sha256,expected_ab_manifest_sha256,run_epoch):
    """Full current checks, reuse their fresh nested AB result, then discard SHA state.

    Every original file read, path/policy check and nested AB verification still
    runs. No result is persisted/reused between calls. Only equal immutable byte
    buffers share SHA work inside this call, before imports and 700-point warmup.
    """
    from startup_digest import StartupDigests
    real=hashlib.sha256;cache=StartupDigests(real);started=time.monotonic_ns()
    cpu=time.thread_time_ns()
    try:
        hashlib.sha256=cache
        checked=verify(root,expected_reuse_manifest_sha256)
        if (checked.get('bundle_validated') is not True
                or checked.get('verified_ab_manifest_sha256')!=expected_ab_manifest_sha256):
            raise ValueError('AB manifest digest differs')
        from status60_ab_manifest import validate_epoch
        validate_epoch(run_epoch)
    finally:
        cache.close();hashlib.sha256=real
    return dict(schema='ps_exact_bytes_validation_prefix_v1',**cache.report(),
        elapsed_ns=time.monotonic_ns()-started,thread_cpu_ns=time.thread_time_ns()-cpu,
        hash_restored=hashlib.sha256 is real,ready_timeout_seconds=60,warmup_slots=700,
        full_new_and_original_ab_checks_retained=True,nested_ab_result_reused=True,
        scope='validation_only_before_PS_imports_and_original700_warmup')


class PrefixReadyConnection:
    def __init__(self,connection,report):self.connection,self.report=connection,report
    def send(self,message):
        if message[:2]==(0,'ready'):
            message=(0,'ready',dict(message[2],ps_validation_prefix=self.report))
        return self.connection.send(message)
    def __getattr__(self,name):return getattr(self.connection,name)


def verified_ps_worker(connection,backend_source,*,root,expected_reuse_manifest_sha256,**kwargs):
    expected_ab=kwargs.pop('expected_manifest_sha256',None);epoch=kwargs.pop('run_epoch',None)
    report=verify_ps_prefix(root,expected_reuse_manifest_sha256,expected_ab,epoch)
    # This is the same post-verification import/root check/call as the retained
    # AB worker. Its full verifier already ran inside this call's new verifier.
    import main_spatial_ps
    from status60_ab_runtime import verify_module_root
    verify_module_root(main_spatial_ps,root)
    return main_spatial_ps.ps_worker(PrefixReadyConnection(connection,report),backend_source,root=root,**kwargs)


def worker(*args,root,expected_reuse_manifest_sha256,**kwargs):
    entered=time.monotonic_ns();verify(root,expected_reuse_manifest_sha256);validated=time.monotonic_ns()
    import status60_ab_runtime as ab
    import joint_startup_worker
    from startup_digest_runtime import prefix_digest_scope
    original_install,original_export=ab.Activation.install,ab.Activation.export
    original_timed=joint_startup_worker.timed_owner_main
    def timed(*a,**kw):
        from ps_early_start import run_early_owner
        return run_early_owner(original_timed,*a,**kw)
    def install(registry):
        # Actual original owner has completed its bootstrap before this call.
        from evidence_reuse import install_reuse
        registry.stack.enter_context(install_reuse())
        original_install(registry)
    def export(registry):
        original_export(registry)  # Retains writer/PS/resource-release gates.
        path=Path(registry.directory)/'evidence-reuse-activation.json'
        with path.open('x',encoding='utf-8') as f:
            json.dump(dict(manifest_sha256=expected_reuse_manifest_sha256,
                input_preparation_only=True,raw_and_processing_states_independent=True,
                fifo_diagnostic_observer_active=False,formal_seconds=60,
                original_ab_events=registry.events,context_bound=registry.prepares==1),f,indent=2)
    with ExitStack() as stack:
        stack.enter_context(ab.replaced(joint_startup_worker,'timed_owner_main',timed))
        stack.enter_context(ab.replaced(ab.Activation,'install',install))
        stack.enter_context(ab.replaced(ab.Activation,'export',export))
        stack.enter_context(ab.replaced(ab,'verified_ps_worker',partial(verified_ps_worker,
            expected_reuse_manifest_sha256=expected_reuse_manifest_sha256)))
        stack.enter_context(prefix_digest_scope(joint_startup_worker,args[1],worker_entry_ns=entered,
            candidate_validation_ns=validated-entered))
        # Return to the unchanged formal60 AB path. The five-second FIFO
        # diagnostic wrapper is preserved on disk, but is not a live dependency.
        return ab.ab_owner_worker(*args,root=root,**kwargs)


def start_owner(context,*args,root,expected_reuse_manifest_sha256,**kwargs):
    if Path(root).resolve()!=Path(__file__).resolve().parent:raise ValueError('reuse owner root differs')
    verify(root,expected_reuse_manifest_sha256)
    child=context.Process(target=partial(worker,root=root,
        expected_reuse_manifest_sha256=expected_reuse_manifest_sha256,**kwargs),args=args,
        name='joint25-evidence-reuse60-owner',daemon=False)
    child.start();return child
