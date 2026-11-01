"""Actual live loader, actual ARM libraries, ordinary allocated RAM only."""
import ctypes as C
import gc
import sys
import time
from pathlib import Path


def probe(root, expected):
    root = Path(root)
    from lean_joint_guard import verify
    verify(root, expected)
    from lean_ps_worker import no_hardware
    from main_ps_exit_worker import defer_offline_pandas
    before_gc = (gc.isenabled(), gc.get_threshold())
    with no_hardware(), defer_offline_pandas(root):
        from lean_joint_runtime import installed
        import spatial_gil_worker as policy
        import main_heart_native_build as build
        from fault_replay_native import builder
        before = (policy.load_candidate, build.load_verified)
        bindings = []
        with installed(root, expected):
            # Exact retained nested loader that failed in live startup.
            with policy.install_policy(root, bindings):
                lib = build.load_verified(root)
                assert lib.arm_capable
                assert lib.entry_trace_report()['calls'] == 0
                for _ in range(2):
                    ram, payload, result, phase = builder(root).ram_transaction_case()
                    ram[1] = 0x20001; ram[3] = 0x74; ram[10] = 65
                    original = bytes(ram)
                    rc = lib.lib.hm_transact_sample(ram, 16384, payload, 22, 1,
                        C.byref(result), 480, time.monotonic() + .040, C.byref(phase))
                    assert rc == 7 and phase.value == 0 and bytes(ram) == original
                    assert lib.failure['error_code'] == 65 and lib.failure['valid_mask'] == 63
                trace = lib.entry_trace_report()
                assert trace['traced_calls'] == trace['ordinary_calls'] == 1
                assert trace['trace']['primary_code'] == 7
        assert before == (policy.load_candidate, build.load_verified)
    assert before_gc == (gc.isenabled(), gc.get_threshold())
    assert not any(n.split('.')[0] in {'pynq','cv2','smbus'} for n in sys.modules)
    return dict(passed=True, hardware_accessed=False, real_live_nested_loader=True,
        actual_arm_libraries=True, allocated_ram_calls=2, bindings=bindings,
        trace=trace, receipt=lib.failure, hooks_restored=True, gc_unchanged=True,
        scope='No sensor, Overlay, MMIO, camera, DMA, or live SAMPLE; ordinary process RAM only')


if __name__ == '__main__':
    import hashlib, json
    root = Path(__file__).resolve().parent
    expected = hashlib.sha256((root/'lean-joint-manifest.json').read_bytes()).hexdigest()
    print(json.dumps(probe(root, expected)), flush=True)
