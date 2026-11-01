"""Private exact ROUND predicate factoring; no added states or cycles."""
import argparse
import json
from pathlib import Path
import re

from .main_spatial_joint import MAIN,prepare,implement
from .main_heart_joint import sha
from .spatial_build import write_new
from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim,run_tool,source_hashes

DECL="    logic packed_overflow;\n"
ASSIGN="        packed_overflow=rounded[53] ? (er>=16'sd1023 && er!=16'sh7fff) : (er>16'sd1023);\n"
OLD="if(packed_exponent>16'sd1023)"
NEW="if(packed_overflow)"


def predicate(exponent,carry):
    return exponent>=1023 and exponent!=32767 if carry else exponent>1023


def transform(original):
    if original.count(OLD)!=1 or original.count('    logic [10:0] encoded_exponent;\n')!=1:
        raise ValueError('retained ROUND predicate/profile changed')
    text=original.replace('    logic [10:0] encoded_exponent;\n','    logic [10:0] encoded_exponent;\n'+DECL)
    anchor="        encoded_exponent=packed_exponent + 16'sd1023;\n"
    if text.count(anchor)!=1:raise ValueError('retained exponent combinational anchor changed')
    return text.replace(anchor,anchor+ASSIGN).replace(OLD,NEW)


def restore(private):
    if private.count(DECL)!=1 or private.count(ASSIGN)!=1 or private.count(NEW)!=1:
        raise ValueError('private predicate diff is not isolated')
    return private.replace(DECL,'').replace(ASSIGN,'').replace(NEW,OLD)


def prove(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    retained=MAIN/'core_src/history100_fp64.sv'
    body=retained.read_text('utf-8');private=transform(body)
    if restore(private)!=body:raise ValueError('non-predicate RTL change')
    fp=output/'history100_fp64.sv'
    with fp.open('x',encoding='utf-8') as f:f.write(private)
    template=Path(__file__).with_name('sim')/'tb_main_spatial_overflow.sv'
    deps=(MAIN/'core_src/history100_mul53.sv',MAIN/'core_src/main_heart_mul53.sv')
    compiled=compile_xsim((fp,*deps,template),'tb_main_spatial_overflow',output)
    ran=run_tool('xsim',['tb_main_spatial_overflow','--R','--log',str(output/'native.log')],output,timeout=180)
    if 'MAIN_SPATIAL_OVERFLOW_PASS checked=131072' not in ran['stdout']:
        raise ValueError('actual RTL exhaustive predicate equivalence incomplete')
    if source_hashes(compiled['source_hashes'])!=compiled['source_hashes']:
        raise ValueError('predicate proof source changed')
    result=dict(schema='v3b25_main_spatial_overflow_equivalence_v1',passed=True,checked=131072,
        original_sha256=sha(retained),private_sha256=sha(fp),compile=compiled,tool_log=ran['log'],
        source_hashes=source_hashes((Path(__file__),retained)),only_overflow_condition_changed=True,
        state_transitions_unchanged=True,cycle_counts_unchanged=True,all_signed16_exponents_and_round_carries=True,
        main_budget_unchanged=True,hardware_accessed=False)
    write_new(output/'equivalence.json',result)
    return result


def prepare_private(candidate,proof):
    proof=Path(proof).resolve();record=json.loads((proof/'equivalence.json').read_bytes())
    if (record.get('passed') is not True or record.get('checked')!=131072
        or source_hashes(record['source_hashes'])!=record['source_hashes']
        or source_hashes(record['compile']['source_hashes'])!=record['compile']['source_hashes']):
        raise ValueError('current exhaustive RTL proof required')
    candidate=Path(candidate).resolve();prepare(candidate)
    original=(MAIN/'core_src/history100_fp64.sv').read_text('utf-8')
    private=(proof/'history100_fp64.sv').read_text('utf-8')
    if restore(private)!=original:raise ValueError('proof not an isolated current-source edit')
    files=[candidate/'core_src/history100_fp64.sv',*list((candidate/'ip_repo').rglob('history100_fp64.sv')),
        *list((candidate/'project').rglob('history100_fp64.sv'))]
    if len(files)<3:raise ValueError('private IP source copies missing')
    for path in files:
        if path.read_text('utf-8')!=original:raise ValueError('private input source differs: '+str(path))
    # These are exclusively generated copies in this new build directory.
    for path in files:path.write_text(private,encoding='utf-8')
    receipt=dict(schema=record['schema'],proof=str(proof/'equivalence.json'),proof_sha256=sha(proof/'equivalence.json'),
        original_sha256=record['original_sha256'],private_sha256=record['private_sha256'],
        files=source_hashes(files),only_overflow_condition_changed=True,cycle_counts_unchanged=True)
    write_new(candidate/'overflow-equivalence.json',receipt)
    return candidate


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--proof',type=Path,required=True)
    p.add_argument('--candidate',type=Path);a=p.parse_args()
    if a.candidate:
        c=prepare_private(a.candidate,a.proof);print('PRIVATE_PREDICATE_PREPARED',flush=True)
        print(json.dumps(implement(c),ensure_ascii=False),flush=True)
    else:print(json.dumps(prove(a.proof),ensure_ascii=False),flush=True)
