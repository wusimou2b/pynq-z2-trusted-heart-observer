"""Warm the original software-only Bridge once, then transfer it to Session25.

No child target, timeout, warmup algorithm, backend binding, or hardware
operation is implemented here. The original validated bridge does that work.
"""
from contextlib import ExitStack
import json
from pathlib import Path
import time


def describe(exc):return dict(type=type(exc).__name__,message=str(exc))


class EarlyPS:
    def __init__(self,trace,stop):
        self.trace,self.stop=trace,stop
        self.bridge=None;self.attempts=self.handoffs=self.close_calls=0
        self.started_ns=self.ready_ns=self.handoff_ns=None
        self.initial_info=None;self.failure=self.cleanup_error=None

    def _validate_unbound(self):
        b=self.bridge;info=b.info()
        if (b.source!='pl_mmio' or b.backend is not None or b._closed or b._fault
                or b._initialized or not b._worker.is_alive()
                or info.get('worker_hardware_imported') is not False
                or info.get('warmup_slots')!=700 or info.get('warmup_raw')!=700
                or info.get('main_heart_mode')!='one_sample_continuous_v1'
                or info.get('hardware_source')!='pl_mmio'
                or any(info.get(k)!=0 for k in ('completed_steps','pl_requests','sample_requests'))):
            raise RuntimeError('early PS is not the original ready unbound main bridge')
        return info

    def start(self,factory):
        self.trace.check('before_early_ps')
        if self.attempts:raise RuntimeError('early PS starts once; no retry')
        self.attempts=1;self.started_ns=time.monotonic_ns()
        try:
            self.bridge=self.trace.call('early_ps_warmup',lambda:factory('pl_mmio'))
            self.initial_info=self._validate_unbound();self.ready_ns=time.monotonic_ns()
            self.trace.check('after_early_ps_ready')
        except BaseException as exc:self.failure=describe(exc);raise

    def take(self,source):
        self.trace.check('before_early_ps_handoff')
        if source!='pl_mmio' or self.bridge is None or self.handoffs:
            raise RuntimeError('early PS handoff source/state differs; no second constructor')
        self._validate_unbound()
        self.handoffs=1;self.handoff_ns=time.monotonic_ns()
        self.trace.record('early_ps_handoff','observed',worker_pid=self.initial_info['worker_pid'])
        return self.bridge

    def finish(self):
        if self.bridge is None or self.handoffs:return
        self.close_calls+=1
        try:self.bridge.close()  # Original one-second policy, exactly once.
        except BaseException as exc:self.cleanup_error=describe(exc)
        # Never abandon an unclaimed child. If original close cannot stop it,
        # retain this scope and its references; no extra kill/restart policy.
        process=self.bridge._worker;notice=time.monotonic()
        while process.is_alive():
            process.join(.1)
            if time.monotonic()-notice>=5:
                print('提前预热的PS尚未退出；保留引用，不重复close、不启动其它入口。',flush=True)
                notice=time.monotonic()
        if self.cleanup_error is not None:
            raise RuntimeError('unclaimed early PS cleanup failed: '+self.cleanup_error['message'])

    def report(self):
        final=None
        if self.bridge is not None:
            try:final=self.bridge.info()
            except BaseException as exc:final=dict(info_error=describe(exc))
        return dict(schema='early_original_ps_single_handoff_v1',attempts=self.attempts,
            handoffs=self.handoffs,unclaimed_close_calls=self.close_calls,
            started_ns=self.started_ns,ready_ns=self.ready_ns,handoff_ns=self.handoff_ns,
            initial_info=self.initial_info,final_info=final,error=self.failure,cleanup_error=self.cleanup_error,
            warmup_slots=700,ready_timeout_seconds=60,startup_timeout_seconds=180,
            original_hardware_order_retained=True,session_owns_transferred_bridge=bool(self.handoffs),
            original_ps_creation_order_retained=False,
            legacy_ps_warmup_trace_scope='session claim-to-handoff; actual700 is early_ps_warmup',
            legacy_original_start_order_flag_scope='hardware lifecycle only; software PS is early',
            original_constructor_and_close_retained=True,automatic_retry=False)


def run_early_owner(original,binding,trace,owner_main,owner_module,*args,release_contract=None):
    """Hook only the existing dependency bootstrap boundary, before prepare()."""
    from joint_startup import replace_attribute
    directory=Path(args[1]);stop=args[3]
    pool=EarlyPS(trace,stop);original_dependencies=owner_module._dependencies
    failure=None
    with ExitStack() as stack:
        def dependencies():
            d=original_dependencies()
            if release_contract is None:
                bootstrap=d.bootstrap
            else:
                from public_live_lower_identity import public_bootstrap
                bootstrap=lambda base,**options:public_bootstrap(base,release_contract,**options)
            def prewarm(*a,**kw):
                result=bootstrap(*a,**kw)
                from effective25 import session
                pool.start(session.Bridge25)
                stack.enter_context(replace_attribute(session,'Bridge25',pool.take))
                return result
            d.bootstrap=prewarm
            if hasattr(d,'prepare'):
                prepare=d.prepare
                def prepared(*a,**kw):
                    session=prepare(*a,**kw)
                    session._preflight.update(software_ps_prewarm_before_video=True,
                        original_ps_creation_order_retained=False,original_hardware_order_retained=True,
                        early_ps_worker_pid=pool.initial_info['worker_pid'])
                    return session
                d.prepare=prepared
            return d
        stack.enter_context(replace_attribute(owner_module,'_dependencies',dependencies))
        try:return original(binding,trace,owner_main,owner_module,*args,
                            release_contract=release_contract)
        except BaseException as exc:
            failure=exc;pool.failure=pool.failure or describe(exc);raise
        finally:
            try:pool.finish()
            except BaseException as exc:
                if failure is None:raise
                print('保留原启动错误；提前PS收尾另报：'+str(exc),flush=True)
            finally:
                with (directory/'early-ps-owner.json').open('x',encoding='utf-8') as f:
                    json.dump(pool.report(),f,ensure_ascii=False,indent=2,allow_nan=False)
