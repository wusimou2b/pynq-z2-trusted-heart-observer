"""Isolated fail-closed timeout response candidate; never changes a deployed bit.

Only *latched watchdog expiry* on legal SAMPLE payload/result/ACK accesses gets
an AXI OKAY response. The expired transaction stays locked, returns no result,
and cannot ACK. The paired C reader must check status before decoding/ACK and
after ACK. Other address, alignment, identity and protocol errors stay SLVERR.
"""
from pathlib import Path
import json
from .main_heart_transaction import stage_sources
from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim,run_tool,source_hashes

ROOT=Path(__file__).resolve().parent
DEPLOYED=Path('E:/Codex-builds/v3b25-main-spatial-overflow-joint-20261027-01/core_src')


def replace_once(body,before,after):
    if body.count(before)!=1:raise ValueError('timeout candidate source anchor changed: '+before)
    return body.replace(before,after)


def safe_axi(body):
    replacements=[
        ("wire snapshot_allowed=", "wire timeout_fault=expire || (locked && error_code==8'h41);\n    wire snapshot_allowed="),
        ("s_axi_rvalid<=1;s_axi_rdata<=read_high ? pvalue[63:32] : pvalue[31:0];\n                s_axi_rresp<=snapshot_allowed && !expire ? 0 : 2;read_pending<=0;",
         "s_axi_rvalid<=1;s_axi_rdata<=timeout_fault ? 0 : (read_high ? pvalue[63:32] : pvalue[31:0]);\n                s_axi_rresp<=timeout_fault || (snapshot_allowed && !expire) ? 0 : 2;read_pending<=0;"),
        ("else if(expire && !(aw_address==8 && w_strobe==15 && w_data==8)) s_axi_bresp<=2;",
         """else if(timeout_fault && w_strobe==15 &&
                    ((aw_address>=16'h40 && aw_address<=16'h94) ||
                     (aw_address==8 && (w_data==2 || w_data==4)))) begin
                    // Fault receipt only: do not write payload, start, ACK,
                    // clear error_code or release the locked transaction.
                    s_axi_bresp<=0;
                end
                else if(expire && !(aw_address==8 && w_strobe==15 && w_data==8)) s_axi_bresp<=2;"""),
        ("if(!snapshot_allowed || expire) s_axi_rresp<=2;\n                    else begin",
         "if(timeout_fault) begin s_axi_rresp<=0;s_axi_rdata<=0;end\n                    else if(!snapshot_allowed || expire) s_axi_rresp<=2;\n                    else begin"),
        ("if(!snapshot_allowed || expire) s_axi_rresp<=2;\n                    else s_axi_rdata<=active",
         "if(timeout_fault) begin s_axi_rresp<=0;s_axi_rdata<=0;end\n                    else if(!snapshot_allowed || expire) s_axi_rresp<=2;\n                    else s_axi_rdata<=active"),
        ("4:s_axi_rdata<=32'h00020000;", "4:s_axi_rdata<=32'h00020001;"),
    ]
    for before,after in replacements:body=replace_once(body,before,after)
    return body


def safe_c(body):
    body=replace_once(body,'    *phase=1;','''    /* A different RTL receipt contract: reject an old bit before writing. */
    *phase=0;
    if((rc=read_reg(mapped,1,deadline,&status))) return rc;
    if(status!=0x00020001u) return 9;
    if((rc=read_reg(mapped,3,deadline,&status))) return rc;
    if(status&15) return 7;
    *phase=1;''')
    body=replace_once(body,'    if(done!=174) return 3;','''    if(done!=174) return 3;
    /* A watchdog can expire between *any* two MMIO reads. Zero-filled late
     * receipts are fault transport, never a valid sample or a fallback. */
    if((rc=read_reg(mapped,3,deadline,&status))) return rc;
    if((status&127)!=114u) return 7;''')
    body=replace_once(body,'    *phase=6;if((rc=write_reg(mapped,2,4,deadline))) return rc;','''    if((rc=read_reg(mapped,3,deadline,&status))) return rc;
    if((status&127)!=114u) return 7;
    *phase=6;if((rc=write_reg(mapped,2,4,deadline))) return rc;''')
    body=replace_once(body,'    if(status&7) return 8;','    if(status&15) return 8;')
    return body


def stage(output,*,numeric=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    sources,frozen=stage_sources(output,fast_arithmetic=True)
    # The real NLMS/heart pipeline uses the original program and coefficients.
    from .main_heart_reference import FROZEN
    from .board.lean_ps_worker import load_original
    from .small_heart_program import export_program
    load_original(FROZEN)
    from entry25_candidate import DelayedPeakChain
    from heart_v3a.runtime_backend import FixedNlmsBackend
    sections=json.loads((FROZEN/'provenance/entry25_board_check.json').read_text('utf-8'))['native_sos_hex']
    sections=tuple(tuple(float.fromhex(v) for v in row) for row in sections)
    if numeric:
        from .main_heart_pipeline import golden_vectors
        golden_vectors(output)
    else:export_program(output,DelayedPeakChain(FixedNlmsBackend()).config,sections)
    # Retain the already deployed timing-equivalent ROUND factoring as well.
    # Refuse unrelated drift instead of silently constructing an older kernel.
    import hashlib
    from .main_spatial_overflow import restore
    fp=output/'history100_fp64.sv';current=(DEPLOYED/'history100_fp64.sv').read_bytes()
    if hashlib.sha256(current).hexdigest()!='bb8a0931f442e77a8cb17759dedeec85a6aac60719c42cfe9adb80cf817896cc':
        raise ValueError('deployed arithmetic identity differs')
    if restore(current.decode('utf-8').replace('\r\n','\n'))!=fp.read_text('utf-8'):
        raise ValueError('deployed arithmetic is not the proven exact factoring')
    fp.write_bytes(current)
    for source in sources:
        if source.read_bytes()!=(DEPLOYED/source.name).read_bytes():
            raise ValueError('unrelated deployed kernel source drift: '+source.name)
    base=next(p for p in sources if p.name=='main_timed_axi.sv')
    target=output/'main_timeout_safe_axi.sv'
    target.write_text(safe_axi(base.read_text('utf-8')),encoding='utf-8')
    c=output/'main_heart_timeout_readback.c'
    c.write_text(safe_c((ROOT/'board/main_heart_readback.c').read_text('utf-8')),encoding='utf-8')
    return tuple(target if p==base else p for p in sources),base,frozen


def run(output,*,candidate):
    sources,base,frozen=stage(output);output=Path(output).resolve()
    if not candidate:sources=tuple(base if p.name=='main_timeout_safe_axi.sv' else p for p in sources)
    text=(ROOT/'sim/tb_main_heart_axi.sv').read_text('utf-8')
    prefix=text[:text.index('    initial begin\n        repeat(4)')]
    proof=(ROOT/'sim/main_heart_timeout_cases.svh').read_text('utf-8')
    proof=proof.replace('CANDIDATE_RESPONSE', '0' if candidate else '2')
    proof=proof.replace('CANDIDATE_VERSION', "32'h00020001" if candidate else "32'h00020000")
    tb=output/'tb_main_heart_timeout.sv'
    tb.write_text((prefix+proof).replace('module tb_main_heart_axi;','module tb_main_heart_timeout;'),encoding='utf-8')
    inputs=(*sources,tb)
    compiled=compile_xsim(inputs,'tb_main_heart_timeout',output)
    ran=run_tool('xsim',['tb_main_heart_timeout','-runall'],output,timeout=300)
    if 'TIMEOUT_CONTAINMENT_PASS' not in ran['stdout'] or source_hashes(inputs)!=compiled['source_hashes']:
        raise RuntimeError('timeout boundary simulation incomplete or source changed')
    result=dict(candidate=candidate,passed=True,hardware_accessed=False,bitstream_built=False,
        real_rtl=True,physical_sigbus_root_cause_proven=False,watchdog_cycles=2_000_000,
        compile=compiled,log=ran['log'],original_sources=frozen)
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def run_full(output):
    """Retained full 1504-vector numerical/protocol suite against new control."""
    import re
    sources,_,frozen=stage(output,numeric=True);output=Path(output).resolve()
    text=(ROOT/'sim/tb_main_heart_axi.sv').read_text('utf-8')
    text=replace_once(text,"if(value!=32'h00020000)","if(value!=32'h00020001)")
    # Exactly the two formerly aborting watchdog paths change their bus receipt.
    before='        wr(8,4,2,2);halt();protocol=protocol+1;'
    text=replace_once(text,before,before.replace('4,2,2','4,0,2'))
    text=replace_once(text,"rd(16'h1000,value,2);wr(8,4,2,2);halt();protocol=protocol+1;",
                     "rd(16'h1000,value,0);wr(8,4,0,2);halt();protocol=protocol+1;")
    tb=output/'tb_main_heart_axi_safe.sv';tb.write_text(text,encoding='utf-8')
    inputs=(*sources,tb);assets=source_hashes(output.glob('*.mem'))
    vectors=source_hashes((output/'main_pipeline_vectors.txt',))
    compiled=compile_xsim(inputs,'tb_main_heart_axi',output)
    ran=run_tool('xsim',['tb_main_heart_axi','-runall'],output,timeout=1800)
    matches=re.findall(r'MAIN_HEART_AXI_PASS points=(\d+) words=(\d+) protocol=(\d+) max_transaction=(\d+)',ran['stdout'])
    if (len(matches)!=1 or tuple(map(int,matches[0][:2]))!=(1504,1237841)
            or source_hashes(inputs)!=compiled['source_hashes'] or source_hashes(assets)!=assets or source_hashes(vectors)!=vectors):
        raise RuntimeError('full saved-data proof incomplete or identity changed')
    result=dict(passed=True,saved_rows=1504,state_words_checked=1237841,protocol_checks=int(matches[0][2]),
        max_transaction_cycles=int(matches[0][3]),full_saved_rows_verified=True,
        compile=compiled,memory_images=assets,vectors=vectors,log=ran['log'],
        hardware_accessed=False,bitstream_built=False,original_sources=frozen)
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def synthesize(output,proof):
    """OOC check only; cannot release a bit or bypass the full numerical gate."""
    import shutil,csv
    proof=Path(proof).resolve();record=json.loads((proof/'result.json').read_bytes())
    if not record.get('passed') or not record.get('candidate'):
        raise ValueError('passing exact deployed timeout boundary proof required')
    inputs=record['compile']['source_hashes']
    if source_hashes(inputs)!=inputs:raise ValueError('boundary RTL source changed')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    sources=[]
    for name in inputs:
        p=Path(name)
        if p.name.startswith('tb_'):continue
        target=output/p.name;shutil.copy2(p,target);sources.append(target)
    top=output/'main_heart_joint_axi.sv';shutil.copy2(DEPLOYED/top.name,top);sources.append(top)
    for p in proof.glob('*.mem'):shutil.copy2(p,output/p.name)
    script=ROOT/'tcl/main_heart_compute_synth.tcl'
    frozen=source_hashes((*sources,*output.glob('*.mem'),script))
    (output/'sources.txt').write_text('\n'.join(p.as_posix() for p in sources)+'\n',encoding='utf-8')
    ran=run_tool('vivado',['-mode','batch','-source',str(script),'-tclargs',str(output)],output,timeout=1800)
    if 'MAIN_HEART_COMPUTE_SYNTH_PASS fp64=1 nlms=1' not in ran['stdout'] or source_hashes(frozen)!=frozen:
        raise ValueError('candidate OOC synthesis incomplete or source changed')
    with (output/'resources.tsv').open() as f:resources=next(csv.DictReader(f,delimiter='\t'))
    result=dict(synthesis_passed=True,source_hashes=frozen,resources=resources,log=ran['log'],
        full_saved_rows_verified=False,joint_timing_verified=False,hardware_accessed=False,bitstream_built=False)
    (output/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result
