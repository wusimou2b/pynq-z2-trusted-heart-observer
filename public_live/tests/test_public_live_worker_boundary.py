"""Software-only seam tests: fake math/native endpoints; no device or SO load."""
import ast
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime'


def module(name, **values):
    result = ModuleType(name)
    result.__dict__.update(values)
    return result


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, RUNTIME / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / 'runtime'
        root.mkdir()
        sections = ((1., 2., 3., 4., 5., 6.),)
        prepared = dict(binary=dict(path=str(root / 'original.so'), sha256='a' * 64),
                        c_sha256='b' * 64, native_manifest_sha256=None,
                        preparation_sha256=None)
        core = SimpleNamespace(implementation='numpy_dtype_dotfunc_100_v2')
        native_load = Mock(return_value=core)
        class Chain:
            def __init__(self, backend):
                self.config = 'unchanged configuration'
                self.output_detector = SimpleNamespace(_sections=sections)
        modules = {
            'small_heart_model': module('small_heart_model', Identity=object, Model=object),
            'small_heart_chain': module('small_heart_chain', make_chain=lambda base: base),
            'statistics25_native': module('statistics25_native', load_native=native_load,
                make_candidate=lambda value: SimpleNamespace(Chain=Chain)),
            'public_live_contract': module('public_live_contract',
                activate_runtime=Mock(return_value=dict(runtime_root=str(root), manifest_sha256='c' * 64)),
                native_context=Mock(return_value=prepared), read_sections=Mock(return_value=sections)),
            'heart_v3a': module('heart_v3a'),
            'heart_v3a.runtime_backend': module('heart_v3a.runtime_backend', FixedNlmsBackend=type('Backend', (), {})),
        }
        with patch.dict(sys.modules, modules), patch('platform.machine', return_value='armv7l'), patch.object(sys, 'platform', 'linux'):
            yield SimpleNamespace(root=root, sections=sections, prepared=prepared,
                modules=modules, native_load=native_load, Chain=Chain)


class WorkerBoundaryTests(unittest.TestCase):
    def test_explicit_release_uses_contract_and_not_historical_proof(self):
        with fixture() as f:
            for name in ('lean_ps_guard', 'entry25_guard'):
                poison = module(name)
                poison.__getattr__ = lambda name: (_ for _ in ()).throw(AssertionError('historical guard used'))
                f.modules[name] = poison
            with patch.dict(sys.modules, f.modules):
                worker = load('worker_boundary_public', 'small_heart_worker.py')
                contract = dict(schema='test', root=str(f.root.parent), expected_manifest_sha256='c' * 64)
                base, config, sections, metadata = worker.load_chain(f.root, release_contract=contract)
            self.assertIs(base, f.Chain)
            self.assertEqual(config, 'unchanged configuration')
            self.assertEqual(sections, f.sections)
            f.native_load.assert_called_once_with(f.prepared['binary'], release_contract=contract)
            self.assertEqual(metadata['entry_confirmation_checks'], 6)
            self.assertIs(metadata['historical_numerical_qualification'], False)
            self.assertIsNone(metadata['native_statistics']['preparation_sha256'])

    def test_release_rejects_historical_source_argument(self):
        with fixture() as f:
            worker = load('worker_boundary_path', 'small_heart_worker.py')
            with self.assertRaisesRegex(ValueError, 'no historical source'):
                worker.load_chain(f.root, f.root.parent / 'old', release_contract={'test': True})
            f.native_load.assert_not_called()

    def test_legacy_default_still_calls_original_verifiers(self):
        with fixture() as f:
            saved = f.root / 'frozen/provenance/entry25_board_check.json'
            saved.parent.mkdir(parents=True)
            saved.write_text(json.dumps({'native_sos_hex': [[v.hex() for v in row] for row in f.sections]}), 'utf-8')
            verify = Mock(return_value=f.prepared)
            original = Mock(return_value=SimpleNamespace())
            identity = Mock(return_value=dict(entry_confirmation_checks=6))
            with patch.dict(sys.modules, {
                'lean_ps_guard': module('lean_ps_guard', verify_source=verify),
                'lean_ps_worker': module('lean_ps_worker', load_original=original),
                'entry25_guard': module('entry25_guard', identity=identity),
            }):
                worker = load('worker_boundary_legacy', 'small_heart_worker.py')
                worker.load_chain(f.root, 'historical source')
            verify.assert_called_once_with(f.root, 'historical source', hardware=False, host_check=False)
            original.assert_called_once_with(f.root / 'frozen')
            f.native_load.assert_called_once_with(f.prepared['binary'])

    def test_wrong_host_abi_refuses_before_native_module_loader(self):
        native = load('native_boundary_actual', 'statistics25_native.py')
        selected = dict(path=str(ROOT / 'synthetic-unused.so'), sha256='a' * 64)
        with patch.dict(sys.modules, {'public_live_contract': module('public_live_contract', native_context=lambda contract: dict(binary=selected))}), patch('platform.machine', return_value='x86_64'), patch.object(native.importlib.util, 'spec_from_file_location', side_effect=AssertionError('native loading reached')):
            with self.assertRaisesRegex(RuntimeError, 'ARMv7'):
                native.load_native(selected, release_contract={'test': True})

    def test_original_numeric_candidate_ast_is_identical(self):
        original = ROOT / 'native_source/statistics25_native.py'
        def candidate(path):
            tree = ast.parse(path.read_text('utf-8'))
            return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'make_candidate')
        self.assertEqual(ast.dump(candidate(original), include_attributes=False),
                         ast.dump(candidate(RUNTIME / 'statistics25_native.py'), include_attributes=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
