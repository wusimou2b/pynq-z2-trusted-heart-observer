import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dma_auditor', ROOT/'scripts/audit_dma_trace.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)


def example(*, direction='send', coherent=False, base=4096, bits=32):
    data = {'schema':'pynq-dma-trace-v1','run_id':'synthetic',
      'buffers':[{'id':'array','owner':'owner','nbytes':64,'device_address':base,'itemsize':4,'coherent':coherent}],
      'channels':[{'id':'dma','owner':'owner','kind':'axi-dma-simple','direction':direction,'data_width_bytes':4,'address_bits':bits,'max_transfer_bytes':4096,'dre':False}], 'events':[]}
    events = []
    if direction == 'send':
        events.append({'event':'cpu_write','buffer':'array'})
        if not coherent: events.append({'event':'sync_to_device','buffer':'array','via':'driver'})
    events += [{'event':'transfer','buffer':'array','channel':'dma','transfer':'tx1','offset':0,'nbytes':64},
               {'event':'complete','channel':'dma','transfer':'tx1','actual_bytes':64}]
    if direction == 'receive':
        if not coherent: events.append({'event':'sync_from_device','buffer':'array','via':'driver'})
        events.append({'event':'cpu_read','buffer':'array'})
    events += [{'event':'free','buffer':'array'}, {'event':'process_exit'}]
    data['events'] = stamp(events)
    return data


def stamp(events):
    return [dict(e, seq=i, ns=i*100, run_id='synthetic', actor=e.get('actor','owner')) for i,e in enumerate(events)]


class TraceTests(unittest.TestCase):
    def check(self,d): return tool.audit(d)
    def reject(self,d): self.assertEqual(self.check(d)['status'],'needs_attention')
    def test_send(self): self.assertEqual(self.check(example())['status'],'consistent_closed')
    def test_receive(self): self.assertEqual(self.check(example(direction='receive'))['status'],'consistent_closed')
    def test_64bit_coherent_image(self):
        r=self.check(example(direction='receive',coherent=True,base=2**32,bits=64))
        self.assertEqual(r['status'],'consistent_closed'); self.assertFalse(r['hardware_cleanup_verified'])
    def test_missing_flush(self):
        d=example();d['events']=stamp([e for e in d['events'] if e['event']!='sync_to_device']);self.reject(d)
    def test_missing_invalidate(self):
        d=example(direction='receive');d['events']=stamp([e for e in d['events'] if e['event']!='sync_from_device']);self.reject(d)
    def test_receive_before_completion(self):
        d=example(direction='receive');d['events']=stamp([e for e in d['events'] if e['event']!='complete']);self.reject(d)
    def test_free_inflight(self):
        d=example();d['events']=stamp([e for e in d['events'] if e['event']!='complete']);self.reject(d)
    def test_stop_request_not_completion(self):
        d=example();d['events']=stamp([{'event':'stop_request','channel':'dma'} if e['event']=='complete' else e for e in d['events']]);self.reject(d)
    def test_valid_cancel(self):
        d=example();d['events']=stamp([{'event':'halted','channel':'dma','driver_verified':True,'active_access_ended':True} if e['event']=='complete' else e for e in d['events']])
        self.assertEqual(self.check(d)['status'],'consistent_closed')
    def test_unproven_halt(self):
        d=example();d['events']=stamp([{'event':'halted','channel':'dma','driver_verified':True,'active_access_ended':False} if e['event']=='complete' else e for e in d['events']]);self.reject(d)
    def test_cancelled_receive_is_not_data(self):
        d=example(direction='receive');d['events']=stamp([{'event':'halted','channel':'dma','driver_verified':True,'active_access_ended':True} if e['event']=='complete' else e for e in d['events']]);self.reject(d)
    def test_stale_epoch(self):
        d=example();d['events'][1]['run_id']='old';self.reject(d)
    def test_wrong_owner(self):
        d=example();d['events'][2]['actor']='other';self.reject(d)
    def test_wrong_completion(self):
        d=example();d['events'][3]['transfer']='other';self.reject(d)
    def test_short_transfer(self):
        d=example();d['events'][3]['actual_bytes']=60;self.reject(d)
    def test_unaligned(self): self.reject(example(base=4097))
    def test_dre_allows_unaligned(self):
        d=example(base=4097);d['channels'][0]['dre']=True
        self.assertEqual(self.check(d)['status'],'consistent_closed')
    def test_address_overflow(self): self.reject(example(base=2**32-32))
    def test_transfer_limit(self):
        d=example();d['channels'][0]['max_transfer_bytes']=32;self.reject(d)
    def test_unknown_dma_mode(self):
        d=example();d['channels'][0]['kind']='axi-vdma';self.reject(d)
    def test_partial_buffer_not_silently_accepted(self):
        d=example();d['events'][2]['nbytes']=32;self.reject(d)
    def test_open_view_blocks_release(self):
        d=example();d['events']=stamp([{'event':'view_open','buffer':'array','view':'slice'}]+d['events']);self.reject(d)
    def test_closed_view(self):
        d=example();d['events']=stamp([{'event':'view_open','buffer':'array','view':'slice'}, {'event':'view_close','buffer':'array','view':'slice'}]+d['events'])
        self.assertEqual(self.check(d)['status'],'consistent_closed')
    def test_borrow_and_return(self):
        d=example();d['channels'][0]['owner']='worker'
        events=[{'event':'borrow','buffer':'array','borrower':'worker'}]+d['events']
        for e in events:
            if e['event'] in ('transfer','complete'):e['actor']='worker'
        events.insert(-2, {'event':'return','buffer':'array','actor':'worker'})
        d['events']=stamp(events);self.assertEqual(self.check(d)['status'],'consistent_closed')
    def test_borrow_not_returned(self):
        d=example();d['events']=stamp([{'event':'borrow','buffer':'array','borrower':'worker'}]+d['events']);self.reject(d)
    def test_double_free(self):
        d=example();d['events'].insert(-1,{'event':'free','buffer':'array'});d['events']=stamp(d['events']);self.reject(d)
    def test_process_exit_does_not_release(self):
        d=example();d['events']=stamp([e for e in d['events'] if e['event']!='free']);self.reject(d)
    def test_timestamp_regression(self):
        d=example();d['events'][2]['ns']=0;self.reject(d)
    def test_missing_event(self):
        d=example();d['events'][2]['seq']=99;self.reject(d)
    def test_fault_remains_after_cleanup(self):
        d=example();d['events'].insert(3,{'event':'wait_timeout','channel':'dma'});d['events']=stamp(d['events'])
        r=self.check(d);self.assertEqual(r['status'],'needs_attention');self.assertTrue(r['declared_resources_released']);self.assertTrue(r['faults'])
    def test_unknown_event(self):
        d=example();d['events'][0]['event']='guess_reset';self.reject(d)
    def test_no_proof_from_empty(self):
        d=example();d['events']=[];self.reject(d)
    def test_overlapping_allocations(self):
        d=example();d['buffers'].append(dict(d['buffers'][0],id='alias'));self.reject(d)
    def test_boolean_size(self):
        d=example();d['buffers'][0]['nbytes']=True;self.reject(d)
    def test_missing_final_free(self):
        d=example();d['events']=d['events'][:-2];self.reject(d)
    def test_cli_input_and_output_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);src=p/'trace.json';src.write_text(json.dumps(example()));before=src.read_bytes();out=p/'result.json'
            cmd=[sys.executable,'-B',str(ROOT/'scripts/audit_dma_trace.py'),'--trace',str(src),'--output',str(out)]
            r=subprocess.run(cmd,capture_output=True);self.assertEqual(r.returncode,0)
            saved=out.read_bytes();r=subprocess.run(cmd,capture_output=True);self.assertNotEqual(r.returncode,0)
            self.assertEqual(out.read_bytes(),saved);self.assertEqual(src.read_bytes(),before)
    def test_json_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json';p.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):tool.load(p)


if __name__=='__main__':unittest.main()
