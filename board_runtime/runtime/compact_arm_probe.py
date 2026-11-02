"""ARM no-hardware tail/IPC qualification from immutable saved receipts."""
import argparse,dataclasses,importlib,json,multiprocessing as mp,sys,time,zipfile,hashlib
from pathlib import Path


def encode(x):
    if dataclasses.is_dataclass(x):
        module=type(x).__module__.removeprefix('v3b25_integration.board.')
        return {'class':module+'.'+type(x).__name__,'fields':{f.name:encode(getattr(x,f.name)) for f in dataclasses.fields(x)}}
    if isinstance(x,tuple):return {'tuple':[encode(v) for v in x]}
    if isinstance(x,dict):return {k:encode(v) for k,v in x.items()}
    if isinstance(x,list):return [encode(v) for v in x]
    if isinstance(x,float):return {'float':x.hex()}
    return x


ALLOWED={'v3a_rate25.frontend.Slot','main_heart_mmio.SampleRequest','main_heart_mmio.SampleResult',
    'small_heart_model.Identity','small_heart_model.BranchResult','heart_v3a.axi_contract.NlmsReply',
    'heart_v3a.runtime_pl_chain.PlRuntimeFrame','heart_v2.runtime_main_chain.RuntimeFrame'}
def decode(x):
    if isinstance(x,list):return [decode(v) for v in x]
    if not isinstance(x,dict):return x
    if set(x)=={'float'}:return float.fromhex(x['float'])
    if set(x)=={'tuple'}:return tuple(decode(v) for v in x['tuple'])
    if set(x)=={'class','fields'}:
        if x['class'] not in ALLOWED:raise ValueError('unexpected fixture class '+x['class'])
        mod,name=x['class'].rsplit('.',1);return getattr(importlib.import_module(mod),name)(**decode(x['fields']))
    return {k:decode(v) for k,v in x.items()}


class Tape:
    source='pl_mmio'
    def __init__(self,rows):self.rows=rows;self.index=0
    def reset(self):return 1
    def identity(self,seq,generation):return self.rows[self.index]['request'].identity
    def sample(self,request):
        from main_rpc_compact import same_request
        row=self.rows[self.index];self.index+=1
        if not same_request(request,row['request']):raise ValueError('saved request/reference mismatch')
        return row['response']


def main():
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/'probe-manifest.json').read_bytes())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:raise ValueError('probe identity differs')
    baseline=root.parent/'v3b25 video startup300 ready60';sys.path.insert(1,str(baseline))
    from lean_ps_worker import no_hardware
    with no_hardware():
        from small_heart_worker import load_chain
        base,_,_,metadata=load_chain(baseline,root.parent/'v3b25 native100 heart video')
        from main_tail_compact import make_chain
        from main_heart_chain import make_chain as original
        from main_rpc_compact import Preparation,same_request,CONTROLS
        from small_heart_model import detector_state
        with zipfile.ZipFile(root/'receipts.zip') as z:rows=decode(json.loads(z.read('rows.json')))
        if len(rows)!=1504:raise ValueError('fixture count differs')
        prep=Preparation('fixture-only');a=original(base)(Tape(rows));b=make_chain(base)(Tape(rows))
        for row in rows:
            request=prep.request(row['slot'],row['request'].identity.request_id,CONTROLS)
            if not same_request(request,row['request']):raise ValueError('ARM owner reference bits differ')
            prep.previous=row['slot']
            left,right=a.step(row['slot']),b.step(row['slot'])
            if encode(left)!=encode(right):raise ValueError('ARM numerical mismatch '+str(row['slot'].sequence))
            if encode(detector_state(a.output_detector))!=encode(detector_state(b.output_detector)):
                raise ValueError('ARM output detector state mismatch')
        del a,b
        result=dict(schema='compact_arm_saved_v1',hardware_accessed=False,count=len(rows),
            all_frame_fields_equal=True,all_owner_reference_bits_equal=True,metadata=metadata,groups=[])
        for label in 'ABBA':
            chain=(original if label=='A' else make_chain)(base)(Tape(rows));start=time.monotonic_ns();cpu=time.process_time_ns()
            for row in rows:chain.step(row['slot'])
            result['groups'].append(dict(group=label,count=len(rows),wall_ns=time.monotonic_ns()-start,cpu_ns=time.process_time_ns()-cpu))
            print('GROUP_DONE',label,flush=True)
        with (root/'arm-results.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False)


if __name__=='__main__':main()
