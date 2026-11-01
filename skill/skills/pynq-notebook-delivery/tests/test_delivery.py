import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/'scripts/notebook_delivery.py'
spec = importlib.util.spec_from_file_location('delivery_tool', SCRIPT)
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)


def notebook():
    return {'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','language':'python','display_name':'Python 3'},
      'language_info':{'name':'python','version':'3.10'}},'cells':[
        {'cell_type':'markdown','metadata':{},'source':['# Array example\n']},
        {'cell_type':'code','metadata':{},'source':['from demo_worker import ready\n','ready(scale=2)'], 'execution_count':None,'outputs':[]}]}


def write_json(path,value):path.write_text(json.dumps(value),encoding='utf8')


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.work=Path(self.temp.name);self.root=self.work/'bundle';self.root.mkdir()
        self.nb=notebook();write_json(self.root/'Demo.ipynb',self.nb)
        self.worker='PURE_PREFLIGHT = True\ndef ready(*, scale):\n    return {"sum": sum([1,2,3])*scale}\n'
        (self.root/'demo_worker.py').write_text(self.worker)
        self.spec={'schema':tool.SPEC,'files':{'delivery-spec.json':'bytes','Demo.ipynb':tool.NOTEBOOK,'demo_worker.py':'bytes'},
                   'entry':{'module':'demo_worker','callable':'ready','kwargs':{'scale':2}},'runtime_dirs':['results']}
        write_json(self.root/'delivery-spec.json',self.spec)
    def seal(self):return tool.seal(self.root,'delivery-spec.json','delivery-manifest.json')['manifest_sha256']
    def verify(self,sha=None):return tool.verify(self.root,'delivery-manifest.json',sha)
    def cli(self,*args,expected=0):
        # Unique output for every call, outside the source bundle.
        out=self.work/('report-'+str(len(list(self.work.glob('report*'))))+'.json')
        p=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(SCRIPT),*args,'--root',str(self.root),'--output',str(out)],capture_output=True,text=True)
        self.assertEqual(p.returncode,expected,p.stdout+p.stderr)
        return json.loads(out.read_text('utf8'))
    def test_seal_and_verify_no_payload_import(self):
        sha=self.seal();doc,r=self.verify(sha)
        self.assertEqual(r['members'],3);self.assertFalse(r['hardware_accessed']);self.assertFalse(r['provenance_verified'])
        self.assertNotIn('demo_worker',sys.modules)
    def test_output_save_preserves_notebook_identity(self):
        sha=self.seal();self.nb['cells'][1].update(outputs=[{'output_type':'stream','text':['saved']}],execution_count=3)
        self.nb['cells'][1]['metadata']['trusted']=True
        self.nb['cells'][1]['id']='new-cell-id';self.nb['metadata']['widgets']={'transient':True}
        self.nb['metadata']['language_info']['version']='3.12.7'
        write_json(self.root/'Demo.ipynb',self.nb);self.verify(sha)
    def test_list_and_string_source_equal(self):
        sha=self.seal();self.nb['cells'][1]['source']=''.join(self.nb['cells'][1]['source'])
        write_json(self.root/'Demo.ipynb',self.nb);self.verify(sha)
    def test_changed_source_rejected(self):
        self.seal();self.nb['cells'][1]['source']=['ready(scale=3)'];write_json(self.root/'Demo.ipynb',self.nb)
        with self.assertRaises(ValueError):self.verify()
    def test_changed_order_rejected(self):
        self.seal();self.nb['cells'].reverse();write_json(self.root/'Demo.ipynb',self.nb)
        with self.assertRaises(ValueError):self.verify()
    def test_execution_tags_rejected_when_changed(self):
        self.seal();self.nb['cells'][1]['metadata']['tags']=['skip-execution'];write_json(self.root/'Demo.ipynb',self.nb)
        with self.assertRaises(ValueError):self.verify()
    def test_kernel_changed(self):
        self.seal();self.nb['metadata']['kernelspec']['name']='other';write_json(self.root/'Demo.ipynb',self.nb)
        with self.assertRaises(ValueError):self.verify()
    def test_attachment_changed(self):
        self.seal();self.nb['cells'][0]['attachments']={'x':{'image/png':'new'}};write_json(self.root/'Demo.ipynb',self.nb)
        with self.assertRaises(ValueError):self.verify()
    def test_empty_notebook_saves_error(self):
        self.seal();(self.root/'Demo.ipynb').write_bytes(b'')
        r=self.cli('verify',expected=2);self.assertFalse(r['passed']);self.assertEqual(r['error']['type'],'JSONDecodeError')
    def test_duplicate_json_field(self):
        (self.root/'Demo.ipynb').write_text('{"nbformat":4,"nbformat":4}')
        with self.assertRaises(ValueError):self.seal()
    def test_nonfinite_numeric_overflow_in_outputs_rejected(self):
        self.nb['cells'][1]['outputs']=[{'value':'REPLACE_OVERFLOW'}]
        (self.root/'Demo.ipynb').write_text(json.dumps(self.nb).replace('"REPLACE_OVERFLOW"','1e400'))
        with self.assertRaises(ValueError):self.seal()
    def test_raw_byte_notebook_policy(self):
        self.spec['files']['Demo.ipynb']='bytes';write_json(self.root/'delivery-spec.json',self.spec)
        self.seal();self.nb['cells'][1]['execution_count']=1;write_json(self.root/'Demo.ipynb',self.nb)
        with self.assertRaises(ValueError):self.verify()
    def test_missing_dependency(self):
        self.seal();(self.root/'demo_worker.py').rename(self.root/'elsewhere.py')
        with self.assertRaises(ValueError):self.verify()
    def test_untracked_source_rejected(self):
        self.seal();(self.root/'old_helper.py').write_text('x=1')
        with self.assertRaises(ValueError):self.verify()
    def test_runtime_data_allowed(self):
        self.seal();(self.root/'results').mkdir();write_json(self.root/'results/receipt.json',{'done':True});self.verify()
    def test_runtime_code_not_allowed(self):
        self.seal();(self.root/'results').mkdir();(self.root/'results/hidden.py').write_text('x=1')
        with self.assertRaises(ValueError):self.verify()
    def test_runtime_directory_cannot_hide_a_regular_file(self):
        self.seal();(self.root/'results').write_text('hidden source')
        with self.assertRaises(ValueError):self.verify()
    def test_spec_must_be_hashed(self):
        self.spec['files'].pop('delivery-spec.json');write_json(self.root/'delivery-spec.json',self.spec)
        with self.assertRaises(ValueError):self.seal()
    def test_traversal_rejected(self):
        for path in ('../outside','/absolute','C:/absolute','x\\y','a//b','a/./b'):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):tool.member(self.root,path)
    def test_existing_manifest_not_overwritten(self):
        self.seal();before=(self.root/'delivery-manifest.json').read_bytes()
        with self.assertRaises(FileExistsError):self.seal()
        self.assertEqual(before,(self.root/'delivery-manifest.json').read_bytes())
    def test_wrong_manifest_pin(self):
        self.seal()
        with self.assertRaises(ValueError):self.verify('0'*64)
    def test_spawn_requires_explicit_execution_and_pin(self):
        self.seal();self.cli('spawn',expected=2)
    def test_spawn_real_partial_keyword_binding(self):
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha)
        self.assertTrue(r['passed']);self.assertTrue(r['natural_exit']);self.assertTrue(r['process_closed'])
        self.assertEqual(r['child']['result'],{'sum':12});self.assertEqual(r['child']['hardware_modules_before_payload'],[])
    def test_actual_missing_import_rejected(self):
        (self.root/'demo_worker.py').write_text('import missing_local_dependency\n'+self.worker)
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertEqual(r['child']['error']['phase'],'import');self.assertTrue(r['natural_exit'])
    def test_preloaded_dependency_cannot_silently_shadow_bundle(self):
        (self.root/'math.py').write_text('def sqrt(x):\n    return 333\n')
        (self.root/'demo_worker.py').write_text('import math\nPURE_PREFLIGHT=True\ndef ready(*,scale):\n    return math.sqrt(9)\n')
        self.spec['files']['math.py']='bytes';write_json(self.root/'delivery-spec.json',self.spec)
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertIn('collide',r['child']['error']['message'])
    def test_child_relative_data_uses_bundle_root(self):
        (self.root/'calibration.json').write_text('{"scale":4}')
        (self.root/'demo_worker.py').write_text('from pathlib import Path\nimport json\nPURE_PREFLIGHT=True\ndef ready(*,scale):\n    return json.loads(Path("calibration.json").read_text())["scale"]\n')
        self.spec['files']['calibration.json']='bytes';write_json(self.root/'delivery-spec.json',self.spec)
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha)
        self.assertEqual(r['child']['result'],4)
    def test_signature_missing_keyword_detected(self):
        self.spec['entry']['kwargs']={};write_json(self.root/'delivery-spec.json',self.spec)
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertEqual(r['child']['error']['phase'],'bind')
    def test_hardware_import_blocked(self):
        (self.root/'demo_worker.py').write_text('import pynq\n'+self.worker)
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertEqual(r['child']['blocked_imports'],['pynq']);self.assertEqual(r['child']['error']['phase'],'import')
    def test_swallowed_hardware_import_still_rejected(self):
        (self.root/'demo_worker.py').write_text('try:\n    import pynq\nexcept ImportError:\n    pass\n'+self.worker)
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertEqual(r['child']['blocked_imports'],['pynq']);self.assertFalse(r['child']['ok'])
    def test_preflight_declaration_required(self):
        (self.root/'demo_worker.py').write_text(self.worker.replace('True','False'))
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertEqual(r['child']['error']['phase'],'import')
    def test_child_error_export_survives_process_close(self):
        (self.root/'demo_worker.py').write_text('PURE_PREFLIGHT=True\ndef ready(*,scale):\n    raise RuntimeError("original-cause")\n')
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertTrue(r['process_closed']);self.assertEqual(r['child']['error']['message'],'original-cause')
    def test_timeout_terminates_only_pure_child(self):
        (self.root/'demo_worker.py').write_text('PURE_PREFLIGHT=True\ndef ready(*,scale):\n    import time\n    time.sleep(20)\n')
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,'--timeout-seconds','1',expected=2)
        self.assertTrue(r['forced_termination']);self.assertFalse(r['natural_exit']);self.assertTrue(r['process_closed'])
    def test_returned_function_but_thread_blocks_natural_exit(self):
        (self.root/'demo_worker.py').write_text('PURE_PREFLIGHT=True\ndef ready(*,scale):\n    import threading,time\n    threading.Thread(target=time.sleep,args=(20,)).start()\n    return 1\n')
        sha=self.seal();r=self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,'--timeout-seconds','1',expected=2)
        self.assertTrue(r['child']['ok']);self.assertEqual(r['error']['phase'],'exit');self.assertFalse(r['natural_exit'])
    def test_member_change_rejected_before_import(self):
        sha=self.seal();marker=self.work/'should-not-exist'
        (self.root/'demo_worker.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("bad")\n'+self.worker)
        self.cli('spawn','--execute-trusted-pure-preflight','--expected-manifest-sha256',sha,expected=2)
        self.assertFalse(marker.exists())
    def test_child_rechecks_before_payload_import(self):
        sha=self.seal();(self.root/'demo_worker.py').write_text(self.worker+'\n# changed')
        class Sink:
            def send_bytes(self,data):self.value=json.loads(data)
            def close(self):pass
        sink=Sink();tool.verified_worker(sink,root=str(self.root),manifest_name='delivery-manifest.json',expected_sha256=sha,run_id='test')
        self.assertEqual(sink.value['error']['phase'],'identity');self.assertFalse(sink.value['ok'])
    def test_unknown_manifest_fields_rejected(self):
        self.seal();p=self.root/'delivery-manifest.json';d=tool.load(p);d['ignore_errors']=True;write_json(p,d)
        with self.assertRaises(ValueError):self.verify()
    def test_cli_report_cannot_replace_source(self):
        self.seal();before=(self.root/'demo_worker.py').read_bytes()
        r=subprocess.run([sys.executable,'-B',str(SCRIPT),'verify','--root',str(self.root),'--output',str(self.root/'demo_worker.py')],capture_output=True)
        self.assertNotEqual(r.returncode,0);self.assertEqual(before,(self.root/'demo_worker.py').read_bytes())


if __name__=='__main__':unittest.main()
