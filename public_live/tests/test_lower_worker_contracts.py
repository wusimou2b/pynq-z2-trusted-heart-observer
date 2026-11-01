import ast
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

TEST_ROOT = Path(__file__).resolve().parent
ROOT = TEST_ROOT.parent / 'runtime'
if not ROOT.is_dir():
    ROOT = TEST_ROOT / 'public_live_release/runtime'


def function(name, module):
    tree = ast.parse((ROOT/module).read_text(encoding='utf-8'))
    return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)


class WorkerContractTests(unittest.TestCase):
    def test_video_contract_is_carried_in_spec_for_compact_process(self):
        f=function('video_child','owner_flat_live_runtime.py')
        calls=[]
        fake=types.ModuleType('compact_delivery_runtime')
        fake.video_child=lambda spec,*args:calls.append(spec)
        ns={'verify_boundary':lambda *a:None}
        exec(compile(ast.Module(body=[f],type_ignores=[]),'<video-only>','exec'),ns)
        contract={'expected_manifest_sha256':'a'*64}
        with patch.dict(sys.modules,{'compact_delivery_runtime':fake}):
            ns['video_child']({'root':'runtime'},'channel',expected='old',release_contract=contract)
        self.assertEqual(calls[0]['release_contract'],contract)

    def test_legacy_held_loader_keeps_original_single_argument_interface(self):
        f=function('install_policy','spatial_gil_worker.py')
        fake=types.ModuleType('main_heart_native_build')
        calls=[]
        fake.load_verified=lambda root:calls.append(root) or types.SimpleNamespace(binding_info={'held':True})
        startup=types.ModuleType('joint_startup')
        @contextmanager
        def replaced(module,name,value):
            old=getattr(module,name);setattr(module,name,value)
            try:yield
            finally:setattr(module,name,old)
        startup.replace_attribute=replaced
        ns={'contextmanager':contextmanager,'Path':Path,'__package__':None,'load_candidate':lambda x:x}
        exec(compile(ast.Module(body=[f],type_ignores=[]),'<policy-only>','exec'),ns)
        with patch.dict(sys.modules,{'main_heart_native_build':fake,'joint_startup':startup}):
            with ns['install_policy'](Path.cwd(),[]):fake.load_verified(Path.cwd())
        self.assertEqual(len(calls),1)

    def test_public_bootstrap_tracks_every_manifest_member(self):
        import importlib.util
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); runtime=root/'runtime'
            (root/'public-live-manifest.json').write_text(json.dumps({'files':[
                {'path':'runtime/source.py','sha256':'b'*64},
                {'path':'runtime/native.so','sha256':'c'*64}]}))
            fake=types.ModuleType('public_live_contract')
            fake.verify_release=lambda c:{'root':str(root),'runtime_root':str(runtime),'manifest_sha256':'a'*64}
            fake.activate_runtime=fake.verify_release;fake.native_context=lambda c:{}
            with patch.dict(sys.modules,{'public_live_contract':fake}):
                spec=importlib.util.spec_from_file_location('bootstrap_under_test',ROOT/'public_live_lower_identity.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                context,_=module.public_bootstrap(runtime/'frozen/base',{},algorithm=True)
            self.assertEqual(set(context['tracked_hashes']),{str(root/'runtime/source.py'),str(root/'runtime/native.so')})
            self.assertFalse(context['historical_numerical_qualification'])

    def test_early_owner_accepts_and_forwards_explicit_contract(self):
        f=function('run_early_owner','ps_early_start.py')
        self.assertIn('release_contract',[a.arg for a in f.args.kwonlyargs])
        calls=[n for n in ast.walk(f) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='original']
        self.assertTrue(calls)
        self.assertTrue(all(any(k.arg=='release_contract' for k in c.keywords) for c in calls))

    def test_load_original_accepts_release_contract(self):
        f = function('load_original','lean_ps_worker.py')
        self.assertIn('release_contract',[a.arg for a in f.args.kwonlyargs])

    def test_public_ps_prefix_does_not_execute_private_manifest_verifier(self):
        f=function('verify_ps_prefix','evidence_reuse_runtime.py')
        ns={'time':time,'verify_boundary':lambda root,c: {'release_manifest_sha256':'a'*64,'historical_numerical_qualification':False}}
        fake=types.ModuleType('status60_ab_manifest');fake.validate_epoch=lambda value:None
        digest=types.ModuleType('startup_digest')
        digest.StartupDigests=lambda *a: (_ for _ in ()).throw(AssertionError('legacy prefix entered'))
        ns['hashlib']=__import__('hashlib')
        with patch.dict(sys.modules,{'status60_ab_manifest':fake,'startup_digest':digest}):
            exec(compile(ast.Module(body=[f],type_ignores=[]),'<prefix-only>','exec'),ns)
            result=ns['verify_ps_prefix']('runtime','old','old','epoch',
                release_contract={'expected_manifest_sha256':'a'*64})
        self.assertEqual(result['schema'],'trusted_heart_public_ps_prefix_v1')
        self.assertFalse(result['historical_numerical_qualification'])

    def test_public_main_ps_uses_no_historical_prepared_directory(self):
        f=function('ps_worker','main_spatial_ps.py')
        calls=[]
        ns={'main_worker':lambda *a,**k:calls.append(k),'ReadyConnection':lambda c:c}
        exec(compile(ast.Module(body=[f],type_ignores=[]),'<ps-only>','exec'),ns)
        contract={'root':'release'}
        ns['ps_worker']('pipe','python_fixed',root='runtime',source='old-original',release_contract=contract)
        self.assertIsNone(calls[0]['prepared_source'])
        self.assertEqual(calls[0]['release_contract'],contract)


if __name__=='__main__':unittest.main()
