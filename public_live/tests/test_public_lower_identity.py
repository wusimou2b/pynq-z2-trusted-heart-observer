import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


TEST_ROOT = Path(__file__).resolve().parent
RUNTIME = TEST_ROOT.parent / 'runtime'
if not RUNTIME.is_dir():
    RUNTIME = TEST_ROOT / 'public_live_release/runtime'
FILE = RUNTIME / 'public_live_lower_identity.py'


class LowerIdentityTests(unittest.TestCase):
    def load(self, verify):
        self.assertTrue(FILE.is_file(), 'public lower identity is not implemented')
        fake = types.ModuleType('public_live_contract')
        fake.verify_release = verify
        fake.native_context = lambda c: {'binary': {'path': 'selected.so', 'sha256': 'a'*64}, 'native_manifest_sha256': None, 'preparation_sha256': None, 'historical_numerical_qualification': False}
        with patch.dict(sys.modules, {'public_live_contract': fake}):
            spec = importlib.util.spec_from_file_location('lower_under_test', FILE)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_runtime_origin_is_enforced(self):
        module = self.load(lambda c: {'runtime_root': str(Path.cwd()/'one'), 'manifest_sha256': 'a'*64})
        with self.assertRaises(ValueError):
            module.verify_boundary(Path.cwd()/'two', {})

    def test_failure_is_propagated_without_success_receipt(self):
        def fail(c): raise ValueError('altered asset')
        module = self.load(fail)
        with self.assertRaisesRegex(ValueError, 'altered asset'):
            module.verify_boundary(Path.cwd(), {})

    def test_public_receipt_does_not_claim_private_qualification(self):
        module = self.load(lambda c: {'runtime_root': str(Path.cwd()), 'manifest_sha256': 'a'*64})
        result = module.verify_boundary(Path.cwd(), {})
        self.assertEqual(result['release_manifest_sha256'], 'a'*64)
        self.assertFalse(result['historical_numerical_qualification'])
        self.assertNotIn('bundle_validated', result)


if __name__ == '__main__': unittest.main()
