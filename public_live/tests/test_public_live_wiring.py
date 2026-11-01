"""Boundary tests use stdlib fakes; no PYNQ, pandas, NumPy or ELF loads."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

_BASE=Path(__file__).resolve().parent
R=(_BASE/'public_live_release/runtime' if (_BASE/'public_live_release/runtime').is_dir()
   else _BASE.parent/'runtime')


def load(name):
    spec=importlib.util.spec_from_file_location(name,R/(name+'.py'))
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


class Process:
    def __init__(self,**kwargs):
        self.kwargs=kwargs;self.started=False;self.exitcode=0;self.alive=False
    def start(self):self.started=True
    def join(self,timeout):self.join_timeout=timeout
    def is_alive(self):return self.alive
    def close(self):self.closed=True


class WiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.contract={'root':str(self.root),'manifest_sha256':'a'*64}
        self.calls=[]
        self.context={'root':str(self.root),'runtime_root':str(self.root),
            'manifest_sha256':'a'*64,'assets':{'native_binary':{'sha256':'b'*64},'native_source':{'sha256':'c'*64}}}
        identity=types.ModuleType('public_live_contract')
        identity.verify_release=self.verify
        demo_guard=types.ModuleType('demo_continuous_guard');demo_guard.verify=self.private_guard
        route_guard=types.ModuleType('route_live_guard');route_guard.verify_new=self.private_guard
        traces=types.ModuleType('lean_ps_exit_trace');traces.make_shared=lambda: {'trace':'same'}
        compact=types.ModuleType('compact_delivery_runtime');compact.video_child=lambda *a: None
        self.patcher=patch.dict(sys.modules,{'public_live_contract':identity,'demo_continuous_guard':demo_guard,
            'route_live_guard':route_guard,'lean_ps_exit_trace':traces,'compact_delivery_runtime':compact})
        self.patcher.start();self.addCleanup(self.patcher.stop)
        self.identity=load('public_live_identity')
        self.ctx=types.SimpleNamespace(Process=self.make_process)
        self.created=[]

    def verify(self,contract):
        self.calls.append(contract)
        if contract != self.contract:raise ValueError('release identity differs')
        return self.context

    def private_guard(self,*a,**k):
        raise AssertionError('private guard must not be invoked on public path')

    def make_process(self,**kwargs):
        p=Process(**kwargs);self.created.append(p);return p

    def test_demo_owner_spawn_carries_contract_and_revalidates(self):
        m=load('demo_continuous_runtime')
        p=m.start_owner(self.ctx,'a','b',root=self.root,demo_expected='a'*64,
                        release_contract=self.contract,expected='a'*64)
        self.assertTrue(p.started)
        self.assertEqual(p.kwargs['target'].keywords['release_contract'],self.contract)
        self.assertEqual(self.calls,[self.contract])

    def test_route_owner_spawn_carries_contract(self):
        m=load('route_live_runtime')
        p=m.start_owner(self.ctx,'a',root=self.root,expected='a'*64,release_contract=self.contract)
        self.assertEqual(p.kwargs['target'].keywords['release_contract'],self.contract)
        self.assertTrue(p.started)

    def test_identity_failure_prevents_owner_creation(self):
        m=load('demo_continuous_runtime')
        with self.assertRaises(ValueError):
            m.start_owner(self.ctx,root=self.root,demo_expected='a'*64,release_contract={'wrong':True})
        self.assertEqual(self.created,[])

    def test_legacy_mode_still_invokes_original_guard(self):
        m=load('demo_continuous_runtime')
        with self.assertRaisesRegex(AssertionError,'private guard'):
            m.start_owner(self.ctx,root=self.root,demo_expected='old')

    def test_video_spec_rejects_mixed_manifest_before_resources(self):
        m=load('compact_video_process')
        spec={'root':str(self.root),'manifest_sha256':'d'*64,'release_contract':self.contract}
        with self.assertRaisesRegex(ValueError,'video process manifest'):
            m.verify_spec(spec)
        spec['manifest_sha256']='a'*64
        self.assertEqual(m.verify_spec(spec)['manifest_sha256'],'a'*64)

    def test_runtime_root_mismatch_is_rejected(self):
        other=self.root/'other';other.mkdir()
        with self.assertRaisesRegex(ValueError,'runtime root differs'):
            self.identity.check_runtime(other,self.contract)

    def test_hardware_identity_keeps_watchdog_and_matched_pair_semantics(self):
        directory=self.root/'compact_hardware';directory.mkdir()
        bit=directory/'heart_v3b25_main.bit';hwh=directory/'heart_v3b25_main.hwh'
        bit.write_bytes(b'synthetic-bit');hwh.write_text('synthetic-hwh')
        self.context['assets'].update(bit={'path':str(bit),'sha256':'d'*64},
                                      hwh={'path':str(hwh),'sha256':'e'*64})
        document={'schema':'timeout_safe_main_spatial_v1','core_version':0x20001,
            'watchdog_cycles':2000000,'static_validation_passed':True,
            'pair':{bit.name:'d'*64,hwh.name:'e'*64},
            'metrics':{'wns_ns':0.2,'whs_ns':0.1,'drc_errors':0,'drc_critical':0}}
        path=directory/'timeout-release.json';path.write_text(json.dumps(document))
        receipt=self.identity.verify_hardware(directory,self.contract)
        self.assertFalse(receipt['historical_numerical_qualification'])
        self.assertEqual(receipt['files'],document['pair'])
        document['watchdog_cycles']=4000000;path.write_text(json.dumps(document))
        with self.assertRaisesRegex(ValueError,'hardware release contract'):
            self.identity.verify_hardware(directory,self.contract)


class ShortProtocolTests(unittest.TestCase):
    def test_short_uses_same_contract_and_original_close_deadline(self):
        contract={'root':'test','manifest_sha256':'a'*64}
        context={'manifest_sha256':'a'*64,'assets':{'native_binary':{'sha256':'b'*64},'native_source':{'sha256':'c'*64}}}
        identity=types.ModuleType('public_live_contract');identity.verify_release=lambda c:context
        ready={'release_manifest_sha256':'a'*64,'historical_numerical_qualification':False,
            'worker_hardware_imported':False,'hardware_source':'python_fixed','entry_confirmation_checks':6,
            'main_heart_mode':'one_sample_continuous_v1','warmup_slots':700,'warmup_raw':700,
            'native_statistics':{'binary_sha256':'b'*64,'c_sha256':'c'*64}}
        class Pipe:
            def __init__(self):self.sent=[]
            def poll(self,seconds):self.poll_seconds=seconds;return True
            def recv(self):return (0,'ready',ready)
            def send(self,message):self.sent.append(message)
            def close(self):pass
        parent,child=Pipe(),Pipe();processes=[]
        def construct(**kwargs):
            p=Process(**kwargs);processes.append(p);return p
        ctx=types.SimpleNamespace(Pipe=lambda:(parent,child),Process=construct)
        with patch.dict(sys.modules,{'public_live_contract':identity}):
            m=load('public_live_runtime')
            with patch.object(m.mp,'get_context',return_value=ctx):result=m.short(contract)
        self.assertTrue(result['passed']);self.assertFalse(result['hardware_accessed'])
        self.assertEqual(parent.poll_seconds,60.)
        self.assertEqual(processes[0].join_timeout,1.)
        self.assertEqual(processes[0].kwargs['args'][1],contract)
        self.assertEqual(parent.sent,[(1,'close',None)])
        self.assertFalse(result['historical_numerical_qualification'])


if __name__=='__main__':unittest.main()
