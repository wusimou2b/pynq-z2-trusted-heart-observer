"""Adapt only the heart backend boundary inside the unchanged hybrid owner."""
from contextlib import contextmanager, ExitStack
from functools import partial
from pathlib import Path
import time
import uuid


class LiveBackend:
    source='pl_mmio'
    def __init__(self,native):
        self.native=native
    @property
    def _fault(self):return self.native.fault
    def reset(self):return self.native.reset()
    def set_deadline(self,value):return self.native.set_deadline(value)
    def sample(self,request):return self.native.sample(request)
    def snapshot(self):
        io=self.native.mmio
        if (io.read(0),io.read(4),io.read(24)) != (0x484d3235,0x20000,self.native.core_epoch):
            raise RuntimeError('main final snapshot identity differs')
        accepted,completed=io.read(32),io.read(36)
        samples=self.native.counts['sample']
        if accepted != completed or completed != samples:
            raise RuntimeError('main final snapshot count differs')
        return dict(schema='v3b25_main_sample_snapshot_v1',accepted=accepted,completed=completed,
                    driver_samples=samples,epoch=self.native.epoch,core_epoch=self.native.core_epoch,
                    legacy_nlms_snapshot_issued=False,nlms_latency_cycles_measured=False)


class MeasuredMain:
    def __init__(self,backend,*,clock=time):
        self.backend,self.source,self.clock=backend,backend.source,clock
        self.last_call_ns=0
    def reset(self):return self.backend.reset()
    def set_deadline(self,value):return self.backend.set_deadline(value)
    def sample(self,request):
        start=self.clock.monotonic_ns()
        try:return self.backend.sample(request)
        finally:self.last_call_ns=self.clock.monotonic_ns()-start
    def snapshot(self):return self.backend.snapshot()


def adapt_main_audit(summary,rows):
    gates=summary['audit25']['gates']
    summary['legacy_nlms_audit']={k:gates.pop(k) for k in ('pl_counts','pl_public') if k in gates}
    snap=summary.get('pl_snapshot') or {}
    count=len(rows)
    gates['main_counts']=bool(count and snap.get('schema')=='v3b25_main_sample_snapshot_v1'
        and snap.get('accepted')==snap.get('completed')==snap.get('driver_samples')==count
        and snap.get('legacy_nlms_snapshot_issued') is False)
    gates['main_public']=bool(count and all(r['backend_source']=='pl_mmio' and int(r['beta_int'])==32212255
        and int(r['pl_sequence'])==int(r['sequence']) and int(r['pl_epoch'])==snap.get('epoch')
        and int(r['pl_latency_cycles'])==0 and not int(r['pl_status'])&8 for r in rows))
    summary['heart_compute_scope']='One validated PL SAMPLE transaction; NLMS per-call cycle field0 means unmeasured. Actual main counters are read independently; no locked legacy mailbox snapshot.'
    summary['capture_basics_completed']=all(gates.values())
    return summary


@contextmanager
def install_main_runtime(root,source):
    if __package__:
        from .lean_ps_worker import load_original
        from .joint_startup import replace_attribute
        from . import hybrid_display,shadow_joint,joint_heart_binding,joint_concurrent_owner
        from .main_spatial_owner import IntegratedOwner
        from .main_spatial_ps import ps_worker
        from .main_heart_process import Bridge
        from .main_heart_guard import verify_release
    else:
        from lean_ps_worker import load_original
        from joint_startup import replace_attribute
        import hybrid_display,shadow_joint,joint_heart_binding,joint_concurrent_owner
        from main_spatial_owner import IntegratedOwner
        from main_spatial_ps import ps_worker
        from main_heart_process import Bridge
        from main_heart_guard import verify_release
    root=Path(root);load_original(root/'frozen')
    from effective25 import session as effective
    run_id='main-spatial-'+uuid.uuid4().hex
    target=partial(ps_worker,root=root,source=source,run_id=run_id)
    def bridge(source_name):
        if source_name!='pl_mmio':raise ValueError('integrated live requires physical main source')
        return Bridge(source_name,target,run_id=run_id)
    def pair(directory):
        if Path(directory).resolve()!=root.resolve():raise ValueError('integrated pair root differs')
        checked=verify_release(root/'hardware')
        return dict(pair_integrity_verified=True,files={
            'heart_v3b25_yuyv.bit':checked['files']['heart_v3b25_main.bit'],
            'heart_v3b25_yuyv.hwh':checked['files']['heart_v3b25_main.hwh']})
    original_heart=joint_heart_binding.JointBinding.prepare
    def heart(binding,*args,**kwargs):
        session=original_heart(binding,*args,**kwargs)
        try:
            if __package__:
                from .main_heart_native_build import load_verified
                from .main_heart_readback import NativeTransactionMain,MappedSnapshot
            else:
                from main_heart_native_build import load_verified
                from main_heart_readback import NativeTransactionMain,MappedSnapshot
            io=binding.owner.heart_mmio()
            native=NativeTransactionMain(io,MappedSnapshot(io,load_verified(root)))
            binding.owner.heart_backend=native
            session.backend=LiveBackend(native)
            session._preflight.update(main_heart_compute=True,main_command_seconds=.020,
                spatial_grid=[4,3],heart_backend_schema='one_sample_continuous_v1')
            return session
        except BaseException:
            session._release_owner()
            raise
    old_binding=hybrid_display.HybridBinding
    class IntegratedBinding(old_binding):
        def __init__(self,*args,**kwargs):
            kwargs['owner_factory']=lambda directory,**kw:IntegratedOwner(Path(directory)/'hardware',**kw)
            super().__init__(*args,**kwargs)
        def prepare(self,*args,**kwargs):
            with replace_attribute(joint_heart_binding.JointBinding,'prepare',heart):
                return super().prepare(*args,**kwargs)
    original_dependencies=joint_concurrent_owner._dependencies
    def dependencies():
        d=original_dependencies();old_assess=d.assess
        def assess(summary,paths):
            result=old_assess(summary,paths)
            from effective25.assessment import rows
            return adapt_main_audit(result,rows(paths.results_csv))
        d.assess=assess
        return d
    with ExitStack() as stack:
        for obj,name,value in ((effective,'Bridge25',bridge),(effective,'MeasuredBackend',MeasuredMain),
            (hybrid_display,'HybridBinding',IntegratedBinding),(shadow_joint,'spatial_prepare_pair',pair),
            (joint_concurrent_owner,'_dependencies',dependencies)):
            stack.enter_context(replace_attribute(obj,name,value))
        yield
