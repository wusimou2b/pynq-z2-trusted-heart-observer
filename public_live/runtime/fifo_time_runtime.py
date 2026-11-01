"""Cold spawn wrapper; hook the actual AB bootstrap and safe export boundary."""
from public_live_lower_identity import verify_boundary, public_prepared
from contextlib import ExitStack
from functools import partial
import json
from pathlib import Path
from fifo_time_guard import verify

def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)

def worker(*args, root, expected_manifest_sha256, run_epoch, expected_fifo_manifest_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        expected_manifest_sha256 = release_contract['expected_manifest_sha256']
        expected_fifo_manifest_sha256 = release_contract['expected_manifest_sha256']
    verify(root, expected_fifo_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    import status60_ab_runtime as ab, status60_runtime as status
    from fifo_time_observer import Trace, observed_sensor
    trace = Trace()
    original_install = ab.Activation.install
    original_export = ab.Activation.export

    def install(registry):
        original_install(registry)
        import heart_axi_live
        registry.stack.enter_context(ab.replaced(heart_axi_live, 'SensorBus', observed_sensor(heart_axi_live.SensorBus, trace)))

    def export(registry):
        original_export(registry)
        report = trace.report()
        report.update(actual_ab_events=registry.events, context_bound=registry.prepares == 1)
        write_new(registry.directory / 'fifo-timing.json', report)
    with ExitStack() as stack:
        stack.enter_context(ab.replaced(ab.Activation, 'install', install))
        stack.enter_context(ab.replaced(ab.Activation, 'export', export))
        stack.enter_context(ab.replaced(status, 'FORMAL_SECONDS', 5))
        return ab.ab_owner_worker(*args, root=root, expected_manifest_sha256=expected_manifest_sha256, run_epoch=run_epoch, **kwargs, release_contract=release_contract)

def start_owner(context, *args, root, expected_manifest_sha256, run_epoch, expected_fifo_manifest_sha256, release_contract=None, **kwargs):
    if release_contract is not None:
        expected_manifest_sha256 = release_contract['expected_manifest_sha256']
        expected_fifo_manifest_sha256 = release_contract['expected_manifest_sha256']
    if Path(root).resolve() != Path(__file__).resolve().parent:
        raise ValueError('FIFO observer root differs')
    verify(root, expected_fifo_manifest_sha256) if release_contract is None else verify_boundary(root, release_contract)
    child = context.Process(target=partial(worker, root=root, expected_manifest_sha256=expected_manifest_sha256, run_epoch=run_epoch, expected_fifo_manifest_sha256=expected_fifo_manifest_sha256, **kwargs, release_contract=release_contract), args=args, name='joint25-fifo-call-timing-five-seconds', daemon=False)
    child.start()
    return child
