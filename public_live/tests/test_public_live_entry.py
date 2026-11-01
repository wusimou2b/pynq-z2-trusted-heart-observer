"""Pure software checks of the new stage gates; no project drivers are imported."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

_BASE=Path(__file__).resolve().parent
ENTRY = (_BASE / "public_live_release/runtime/public_live_entry.py"
         if (_BASE / "public_live_release/runtime").is_dir()
         else _BASE.parent / "runtime/public_live_entry.py")


class PublicLiveEntryTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(ENTRY.is_file(), "public LIVE entry is not implemented")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "runtime").mkdir()
        self.calls = []
        self.contract = {"root": str(self.root), "manifest_sha256": "a" * 64}
        identity = types.ModuleType("public_live_contract")
        identity.make_contract = lambda root, expected: self.contract
        identity.verify_release = self.verify
        backend = types.ModuleType("public_live_runtime")
        dependencies=types.ModuleType('public_live_dependencies')
        # Stage tests explicitly replace this boundary. Its successful return
        # is not evidence that the real PC or board dependencies are complete.
        dependencies.require_dependencies=lambda: {'modules_available':True}
        dependencies.dependency_report=lambda: {'modules_available':True,'missing':[],
            'target_abi_matches':True,'versions':{'numpy':'1.21.5'}}
        for name, answer in (("short", {"passed": True, "hardware_accessed": False}),
                             ("preview20", {"ownership_qualification_passed": True}),
                             ("prepare", {"prepared": True, "hardware_accessed": False}),
                             ("run", {"manual_session_passed": False, "resources_released": True})):
            setattr(backend, name, self.operation(name, answer))
        self.mods = patch.dict(sys.modules, {"public_live_contract": identity, "public_live_runtime": backend,
                                            'public_live_dependencies':dependencies})
        self.mods.start()
        self.addCleanup(self.mods.stop)
        spec = importlib.util.spec_from_file_location("tested_public_live_entry", ENTRY)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        # This fixture supplies a synthetic release root, so bind the tested
        # module's declared location to that fixture without touching sources.
        self.module.__file__=str(self.root/'runtime/public_live_entry.py')
        self.session = self.module.PublicLiveSession(self.root, "a" * 64)

    def verify(self, contract):
        self.calls.append(("verify", contract))
        return {"root": str(self.root), "runtime_root": str(self.root / "runtime"),
                "manifest_sha256": "a" * 64, "assets": {}}

    def operation(self, name, answer):
        def call(contract):
            self.calls.append((name, contract))
            return dict(answer)
        return call

    def test_live_gate_cannot_start_before_short_preview_and_prepare(self):
        with self.assertRaises(ValueError):
            self.session.run(hardware=True, confirmation="RUN-PUBLIC-LIVE25")
        self.assertNotIn("run", [c[0] for c in self.calls])

    def test_preview_requires_exact_hardware_confirmation(self):
        self.session.short()
        with self.assertRaises(ValueError):
            self.session.preview20(hardware=True, confirmation="wrong")
        self.assertNotIn("preview20", [c[0] for c in self.calls])

    def test_stage_identity_is_revalidated_and_contract_reaches_each_backend(self):
        self.session.short()
        self.session.preview20(hardware=True, confirmation="RUN-PUBLIC-VIDEO20")
        self.session.prepare()
        final = self.session.run(hardware=True, confirmation="RUN-PUBLIC-LIVE25")
        self.assertFalse(final["historical_numerical_qualification"])
        self.assertFalse(final["new_release_board_verified"])
        stages = [c for c in self.calls if c[0] != "verify"]
        self.assertEqual([s[0] for s in stages], ["short", "preview20", "prepare", "run"])
        self.assertTrue(all(c[1] == self.contract for c in stages))
        self.assertGreaterEqual(sum(c[0] == "verify" for c in self.calls), 5)

    def test_failed_identity_prevents_backend_work(self):
        self.module.verify_release = lambda contract: (_ for _ in ()).throw(ValueError("identity differs"))
        with self.assertRaisesRegex(ValueError, "identity differs"):
            self.session.short()
        self.assertNotIn("short", [c[0] for c in self.calls])

    def test_existing_attempt_is_preserved_and_not_retried(self):
        self.session.short()
        with self.assertRaises(FileExistsError):
            self.session.short()
        self.assertEqual(sum(c[0] == "short" for c in self.calls), 1)

    def test_unpassed_preview_cannot_prepare(self):
        self.session.short()
        sys.modules["public_live_runtime"].preview20 = self.operation("preview20", {"ownership_qualification_passed": False})
        self.session.preview20(hardware=True, confirmation="RUN-PUBLIC-VIDEO20")
        with self.assertRaises(ValueError):
            self.session.prepare()
        self.assertNotIn("prepare", [c[0] for c in self.calls])

    def test_missing_pandas_is_rejected_before_preview_backend(self):
        self.session.short()
        def missing():raise RuntimeError('dependencies missing before hardware: pandas')
        sys.modules['public_live_dependencies'].require_dependencies=missing
        with self.assertRaisesRegex(RuntimeError,'pandas'):
            self.session.preview20(hardware=True,confirmation='RUN-PUBLIC-VIDEO20')
        self.assertNotIn('preview20',[c[0] for c in self.calls])

    def test_missing_dependency_refuses_short_without_attempt_or_native_backend(self):
        def missing():raise RuntimeError('dependencies missing before hardware: pandas')
        sys.modules['public_live_dependencies'].require_dependencies=missing
        with self.assertRaisesRegex(RuntimeError,'pandas'):
            self.session.short()
        self.assertFalse((self.root/'runtime/public-short-attempt.json').exists())
        self.assertFalse((self.root/'runtime/public-short.json').exists())
        self.assertNotIn('short',[c[0] for c in self.calls])

    def test_wrong_target_abi_refuses_short_without_attempt(self):
        def wrong_abi():raise RuntimeError('requires CPython3.10 ARMv7 hard-float target ABI')
        sys.modules['public_live_dependencies'].require_dependencies=wrong_abi
        with self.assertRaisesRegex(RuntimeError,'target ABI'):
            self.session.short()
        self.assertFalse((self.root/'runtime/public-short-attempt.json').exists())
        self.assertNotIn('short',[c[0] for c in self.calls])

    def test_check_reports_incomplete_dependencies_without_starting_short(self):
        sys.modules['public_live_dependencies'].dependency_report=lambda: {
            'modules_available':False,'missing':['pandas'],'target_abi_matches':False,
            'versions':{'numpy':None}}
        report=self.session.check()
        self.assertIn('dependency_complete',report)
        self.assertFalse(report['dependency_complete'])
        self.assertFalse((self.root/'runtime/public-short-attempt.json').exists())
        self.assertNotIn('short',[c[0] for c in self.calls])


if __name__ == "__main__":
    unittest.main()
