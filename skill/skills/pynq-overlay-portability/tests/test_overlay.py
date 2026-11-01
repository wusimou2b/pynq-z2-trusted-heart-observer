import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


tool = module('overlay_inspector', ROOT/'scripts/inspect_overlay.py')
factory = module('driver_example', ROOT/'assets/driver_factory.py')
env = module('environment_collector', ROOT/'scripts/collect_environment.py')


def fixture(device='7z020', package='clg400', base='0x40000000'):
    return f'''<EDKSYSTEM VIVADOVERSION="fixture-only"><SYSTEMINFO DEVICE="{device}" PACKAGE="{package}"/>
    <MODULES><MODULE FULLNAME="/stream/dma_a" INSTANCE="dma_a" VLNV="xilinx.com:ip:axi_dma:7.1">
    <PARAMETERS><PARAMETER NAME="C_INCLUDE_SG" VALUE="0"/></PARAMETERS></MODULE></MODULES>
    <MEMRANGES><MEMRANGE INSTANCE="stream/dma_a" BASEVALUE="{base}" HIGHVALUE="{hex(int(base,16)+65535)}" MEMTYPE="REGISTER" MASTERBUSINTERFACE="CPU" SLAVEBUSINTERFACE="S_AXI_LITE"/></MEMRANGES></EDKSYSTEM>'''


def profile(device='7z020', package='clg400', bits=32):
    return {'schema': 'pynq-overlay-profile-v1', 'target': {'DEVICE': device, 'PACKAGE': package},
            'required_ips': [{'role': 'stream_transfer', 'vlnv': 'xilinx.com:ip:axi_dma:7.1',
              'parameters': {'C_INCLUDE_SG': '0'}, 'address': {'address_bits': bits, 'min_bytes': 4096}}]}


class InspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.hwh = self.root/'sample.hwh'; self.hwh.write_text(fixture(), encoding='utf8')
        self.p = self.root/'profile.json'; self.doc = profile()
    def run_profile(self, **kw):
        self.p.write_text(json.dumps(self.doc), encoding='utf8')
        return tool.inspect(self.hwh, self.p, **kw)
    def test_metadata_only_not_board_proof(self):
        r = self.run_profile()
        self.assertEqual(r['status'], 'metadata_only')
        self.assertFalse(r['hardware_accessed']); self.assertFalse(r['board_compatibility_verified'])
        self.assertEqual(r['matches'][0]['instance'], 'stream/dma_a')
    def test_64_bit_target_independent_of_board_name(self):
        self.hwh.write_text(fixture('zu3eg', 'sbva484', '0x100000000'))
        self.doc = profile('zu3eg', 'sbva484', 64)
        self.assertFalse(self.run_profile()['errors'])
    def test_target_reject(self):
        self.doc['target']['DEVICE'] = 'zu3eg'; self.assertTrue(self.run_profile()['errors'])
    def test_missing_target_information(self):
        self.doc['target']['ARCH'] = 'zynq'; self.assertTrue(self.run_profile()['errors'])
    def test_unknown_profile_field(self):
        self.doc['assume_compatible'] = True; self.assertTrue(self.run_profile()['errors'])
    def test_non_object_profile(self):
        self.doc = []; self.assertTrue(self.run_profile()['errors'])
    def test_missing_ip(self):
        self.doc['required_ips'][0]['vlnv'] = 'custom:ip:filter:1.0'; self.assertTrue(self.run_profile()['errors'])
    def test_empty_vlnv_component(self):
        self.doc['required_ips'][0]['vlnv'] = 'custom::filter:1.0'
        self.assertTrue(self.run_profile()['errors'])
    def test_parameter_difference(self):
        self.doc['required_ips'][0]['parameters']['C_INCLUDE_SG'] = '1'; self.assertTrue(self.run_profile()['errors'])
    def test_ambiguous_ip_requires_instance(self):
        text = fixture().replace('</MODULES>', '<MODULE FULLNAME="/other" INSTANCE="other" VLNV="xilinx.com:ip:axi_dma:7.1"/></MODULES>')
        self.hwh.write_text(text)
        self.assertTrue(self.run_profile()['errors'])
        self.doc['required_ips'][0]['instance'] = 'stream/dma_a'
        self.assertFalse(self.run_profile()['errors'])
    def test_duplicate_module(self):
        self.hwh.write_text(fixture().replace('</MODULES>', '<MODULE FULLNAME="/stream/dma_a"/></MODULES>'))
        self.assertTrue(self.run_profile()['errors'])
    def test_missing_range(self):
        self.hwh.write_text(fixture().replace('INSTANCE="stream/dma_a"', 'INSTANCE="unmapped"'))
        self.assertTrue(self.run_profile()['errors'])
    def test_address_width(self):
        self.hwh.write_text(fixture(base='0x100000000')); self.assertTrue(self.run_profile()['errors'])
    def test_range_too_small(self):
        self.doc['required_ips'][0]['address']['min_bytes'] = 65537
        self.assertTrue(self.run_profile()['errors'])
    def test_dtd_rejected(self):
        self.hwh.write_text('<!DOCTYPE x [<!ENTITY a "x">]>'+fixture())
        self.assertTrue(self.run_profile()['errors'])
    def test_malformed_xml(self):
        self.hwh.write_text('<EDKSYSTEM>'); self.assertTrue(self.run_profile()['errors'])
    def test_utf16_entity_not_expanded(self):
        self.hwh.write_bytes(('<!DOCTYPE x [<!ENTITY a "x">]>'+fixture()).encode('utf-16'))
        self.assertTrue(self.run_profile()['errors'])
    def test_duplicate_json(self):
        self.p.write_text('{"schema":1,"schema":2}')
        self.assertTrue(tool.inspect(self.hwh, self.p)['errors'])
    def test_matching_pins_are_not_provenance(self):
        bit = self.root/'sample.bit'; bit.write_bytes(b'synthetic non-programmable bytes')
        self.doc['artifact_sha256'] = {'bit': tool.digest(bit), 'hwh': tool.digest(self.hwh)}
        r = self.run_profile(bit=bit)
        self.assertTrue(r['both_artifact_pins_match']); self.assertFalse(r['pair_provenance_verified'])
        bit.write_bytes(b'changed'); self.assertTrue(self.run_profile(bit=bit)['errors'])
    def test_filename_pair(self):
        bit = self.root/'other.bit'; bit.write_bytes(b'fixture'); self.assertTrue(self.run_profile(bit=bit)['errors'])
    def test_environment_absent_is_unknown(self):
        self.doc['required_pynq_versions'] = ['3.1.1']
        self.assertTrue(any('environment absent' in x for x in self.run_profile()['unknowns']))
    def test_environment_version(self):
        self.doc['required_pynq_versions'] = ['3.1.1']
        f = self.root/'env.json'; f.write_text(json.dumps({'schema':'pynq-environment-v1','pynq_version':'2.7'}))
        self.assertTrue(self.run_profile(environment=f)['errors'])
    def test_environment_collector_no_hardware(self):
        r = env.collect(); self.assertFalse(r['hardware_accessed']); self.assertNotIn('pynq', sys.modules)
    def test_cli_preserves_existing_output(self):
        self.run_profile(); out = self.root/'keep.json'; out.write_bytes(b'keep')
        cmd = [sys.executable,'-B',str(ROOT/'scripts/inspect_overlay.py'),'--hwh',str(self.hwh),'--profile',str(self.p),'--output',str(out)]
        r = subprocess.run(cmd, capture_output=True)
        self.assertNotEqual(r.returncode, 0); self.assertEqual(out.read_bytes(), b'keep')


class DriverTests(unittest.TestCase):
    def setUp(self):
        class Dummy:
            calls = 0
            def __init__(self, desc): Dummy.calls += 1
            def read(self, offset): return offset + 100
        self.base = Dummy
        self.cls = factory.make_driver(Dummy,vlnv='example:ip:adder:1.0',readable_registers={'status':4})
    def test_bind_and_read_only_declared(self):
        d = self.cls({'type':'example:ip:adder:1.0','addr_range':4096})
        self.assertEqual(d.read_declared('status'),104)
        with self.assertRaises(KeyError): d.read_declared('unknown')
    def test_wrong_identity_before_constructor(self):
        with self.assertRaises(ValueError): self.cls({'type':'other','addr_range':4096})
        self.assertEqual(self.base.calls,0)
    def test_range_before_constructor(self):
        with self.assertRaises(ValueError): self.cls({'type':'example:ip:adder:1.0','addr_range':4})
        self.assertEqual(self.base.calls,0)
    def test_misalignment(self):
        with self.assertRaises(ValueError): factory.make_driver(self.base,vlnv='example:ip:adder:1.0',readable_registers={'bad':1})
    def test_empty_identity_rejected_by_factories(self):
        with self.assertRaises(ValueError): factory.make_driver(self.base,vlnv='example::adder:1.0',readable_registers={})
        h = module('hierarchy_empty', ROOT/'assets/hierarchy_factory.py')
        with self.assertRaises(ValueError): h.make_hierarchy_driver(self.base,required_ips={'filter':'example:ip:filter:'})
    def test_non_mapping_description_before_constructor(self):
        with self.assertRaises(ValueError): self.cls(None)
        h = module('hierarchy_none', ROOT/'assets/hierarchy_factory.py')
        cls = h.make_hierarchy_driver(self.base,required_ips={'filter':'example:ip:filter:1.0'})
        self.assertFalse(cls.checkhierarchy(None))
        with self.assertRaises(ValueError): cls(None)
        self.assertEqual(self.base.calls,0)
    def test_hierarchy_capabilities(self):
        h = module('hierarchy_example', ROOT/'assets/hierarchy_factory.py')
        cls = h.make_hierarchy_driver(self.base, required_ips={'filter':'example:ip:filter:1.0'})
        self.assertTrue(cls.checkhierarchy({'ip':{'filter':{'type':'example:ip:filter:1.0'}}}))
        self.assertFalse(cls.checkhierarchy({'ip':{'filter':{'type':'example:ip:filter:2.0'}}}))
        with self.assertRaises(ValueError):cls({'ip':{}})
        self.assertEqual(self.base.calls,0)


if __name__ == '__main__': unittest.main()
