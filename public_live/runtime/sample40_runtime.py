"""25Hz candidate: SAMPLE40 only; original initialization/STOP20 retained."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import contextmanager
from functools import partial
from pathlib import Path
if __package__:
    from .main_heart_readback import NativeTransactionMain, MappedSnapshot
else:
    from main_heart_readback import NativeTransactionMain, MappedSnapshot
HARD_SECONDS = 0.04
WARNING_NS = 20000000
TAIL_LIMIT = 64

class Sample40Snapshot(MappedSnapshot):

    def transact(self, deadline, valid):
        try:
            return super().transact(deadline, valid)
        except TimeoutError as exc:
            raise TimeoutError(str(exc).replace('whole20ms', 'whole40ms')) from exc

class Sample40Main(NativeTransactionMain):

    def __init__(self, *args, **kwargs):
        self.initialize_metrics()
        super().__init__(*args, **kwargs)

    def initialize_metrics(self):
        self._sample40_active = False
        self._sample40_boundary = None
        self._over20 = 0
        self._max_transaction_ns = 0
        self._tails = []
        self._failure40 = None

    def _begin(self):
        if not self._sample40_active:
            return super()._begin()
        self._sample40_boundary = 'python_begin'
        self.started = self.clock()
        self.active_deadline = self.started + HARD_SECONDS
        if self.deadline is not None:
            self.active_deadline = min(self.active_deadline, self.deadline)
        self._time()
        self._sample40_boundary = 'python_after_native_success'

    def _time(self):
        if not self._sample40_active:
            return super()._time()
        now = self.clock()
        if self.active_deadline is not None and now >= self.active_deadline:
            if self._failure40 is None:
                self._failure40 = dict(origin=self._sample40_boundary, started=self.started, active_deadline=self.active_deadline, original_step_deadline=self.deadline, guard_checked_now=now, elapsed_seconds=now - self.started, limiting_deadline='original_step' if self.active_deadline == self.deadline else 'sample40')
            raise TimeoutError('continuous whole40ms transaction/step deadline expired; no retry')
        return now

    def observe(self, result):
        ns = round(result.transaction_seconds * 1000000000)
        self._max_transaction_ns = max(self._max_transaction_ns, ns)
        if ns > WARNING_NS:
            self._over20 += 1
            if len(self._tails) < TAIL_LIMIT:
                self._tails.append(dict(sequence=result.identity.sequence, generation=result.identity.generation, request_id=result.identity.request_id, transaction_ns=ns))

    def sample(self, request):
        self._sample40_active = True
        try:
            result = super().sample(request)
            self.observe(result)
            return result
        except BaseException as exc:
            if self._failure40 is None:
                self._failure40 = dict(origin='native_transaction' if isinstance(exc, TimeoutError) else 'original_validation_or_other', native_phase=int(self.reader.phase.value), sequence=request.identity.sequence, error_type=type(exc).__name__, message=str(exc))
            raise
        finally:
            self._sample40_active = False

    def audit(self):
        return dict(schema='sample40_transaction_budget_v1', sample_hard_seconds=HARD_SECONDS, warning_seconds=0.02, main_init_stop_seconds=0.02, successful_samples=self.counts['sample'], over20_transactions=self._over20, max_successful_transaction_ns=self._max_transaction_ns, first_longtails=list(self._tails), retained_longtail_limit=TAIL_LIMIT, failure=self._failure40, new_clock_calls=0, new_per_sample_ipc_messages=0, scope='Existing receipt transaction_seconds; first64transaction tails bounded. Complete-call tails exported from original stoppedCSV separately.')

@contextmanager
def install_runtime(instances):
    if __package__:
        from . import main_heart_readback as native, hybrid_display
        from .joint_startup import replace_attribute
    else:
        import main_heart_readback as native, hybrid_display
        from joint_startup import replace_attribute
    original_prepare = hybrid_display.HybridBinding.prepare

    class ObservedMain(Sample40Main):

        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            instances.append(self)

    def prepare(binding, *a, **kw):
        session = original_prepare(binding, *a, **kw)
        session._preflight.update(main_command_seconds=HARD_SECONDS, main_warning_seconds=0.02, main_init_stop_seconds=0.02, transaction_budget_candidate='sample40_warning20_v1')
        return session
    with replace_attribute(native, 'NativeTransactionMain', ObservedMain), replace_attribute(native, 'MappedSnapshot', Sample40Snapshot), replace_attribute(hybrid_display.HybridBinding, 'prepare', prepare):
        yield

def owner_worker(*args, release_contract=None, **kwargs):
    if __package__:
        from .run_sample40 import verify_package, write_new
        from .spatial_gil_worker import owner_worker as original
    else:
        from run_sample40 import verify_package, write_new
        from spatial_gil_worker import owner_worker as original
    verify_package(kwargs['root']) if release_contract is None else verify_boundary(kwargs['root'], release_contract)
    instances = []
    failure = None
    try:
        with install_runtime(instances):
            return original(*args, **kwargs, release_contract=release_contract)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        report = dict(schema='sample40_owner_budget_v1', instances=len(instances), transaction=instances[0].audit() if len(instances) == 1 else None, original_error=dict(type=type(failure).__name__, message=str(failure)) if failure else None, original_gil_ps_sensor_video_mpu_and_display_retained=True)
        try:
            write_new(Path(args[1]) / 'sample40-owner.json', report)
        except BaseException as export_error:
            if failure is not None:
                raise failure from export_error
            raise

def start_owner(context, *args, release_contract=None, **kwargs):
    child = context.Process(target=partial(owner_worker, **kwargs, release_contract=release_contract), args=args, name='joint25-sample40-warning20-owner', daemon=False)
    child.start()
    return child
