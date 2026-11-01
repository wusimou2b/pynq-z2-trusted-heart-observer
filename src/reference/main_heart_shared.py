"""Private shared-arithmetic derivatives, with unchanged source controls.

The derivatives expose existing arithmetic handshakes, not new host calls.
Standalone golden-tested modules and the original release are never rewritten.
"""
import hashlib
import csv
import json
import re
import shutil
import random
from pathlib import Path

from .main_heart_operators import write_log_assets,write_gain_assets
from .main_heart_welch import write_welch_assets
from .main_heart_fusion import vectors
from .history100_dsp import stage
from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim,run_tool,source_hashes

ROOT=Path(__file__).resolve().parent
OPERATORS=('log10','welch','pow2','gain_argument','fusion','sqrt')
PORTS='''
    output logic shared_req_valid,
    input logic shared_req_ready,
    output logic [1:0] shared_op,
    output logic [63:0] shared_a,shared_b,
    input logic shared_rsp_valid,
    output logic shared_rsp_ready,
    input logic [63:0] shared_value,
    input logic [3:0] shared_faults'''


def stage_arithmetic(output):
    original=stage(output/'history100_fp64_unbuffered.sv')
    text=original.read_text(encoding='utf-8')
    anchor='history100_mul53 multiply('
    if text.count(anchor)!=1:raise ValueError('private multiplier anchor changed')
    # Private derivative only. Keep normal inputs on the original fast path;
    # separate subnormal leading-zero count from variable shift/exponent update.
    changes=[
        ('IDLE, DECODE, NA, NB, EXECUTE, ALIGN,','IDLE, DECODE, NA, NA_APPLY, NB, NB_APPLY, EXECUTE, ALIGN,'),
        ('    logic [52:0] ma, mb;', '    logic [52:0] ma, mb;\n    (* keep="true",dont_touch="true" *) logic [5:0] normal_shift;'),
        ('            ma<=0;mb<=0;ea<=0;eb<=0;er<=0;sig<=0;',
         '            ma<=0;mb<=0;ea<=0;eb<=0;er<=0;sig<=0;normal_shift<=0;'),
        ('''            NA: begin
                if(!ma[52]) begin ma<=ma<<leading_shift(ma);ea<=ea-$signed({10'b0,leading_shift(ma)});end
                state<=NB;
            end
            NB: begin
                if(!mb[52]) begin mb<=mb<<leading_shift(mb);eb<=eb-$signed({10'b0,leading_shift(mb)});end
                state<=EXECUTE;
            end''', '''            NA: begin
                if(ma[52]) state<=NB;
                else begin normal_shift<=leading_shift(ma);state<=NA_APPLY;end
            end
            NA_APPLY: begin
                ma<=ma<<normal_shift;ea<=ea-$signed({10'b0,normal_shift});state<=NB;
            end
            NB: begin
                if(mb[52]) state<=EXECUTE;
                else begin normal_shift<=leading_shift(mb);state<=NB_APPLY;end
            end
            NB_APPLY: begin
                mb<=mb<<normal_shift;eb<=eb-$signed({10'b0,normal_shift});state<=EXECUTE;
            end''')]
    for before,after in changes:
        if text.count(before)!=1:raise ValueError('private normalization anchor changed')
        text=text.replace(before,after)
    target=output/'history100_fp64.sv'
    with target.open('x',encoding='utf-8') as stream:stream.write(text.replace(anchor,'main_heart_mul53 multiply('))
    return target


def call_ports(text,start):
    """Parse only a balanced named-port instance; reject ambiguous edits."""
    opening=text.index('(',start);depth=1;at=opening+1;parts=[];first=at
    while depth and at<len(text):
        if text[at]=='(':depth+=1
        elif text[at]==')':depth-=1
        if (text[at]==',' and depth==1) or depth==0:
            parts.append(text[first:at].strip());first=at+1
        at+=1
    if depth or text[at:at+1]!=';':raise ValueError('unrecognized instance')
    pairs={}
    for part in parts:
        found=re.fullmatch(r'\.(\w+)\((.*)\)',part,re.S)
        if found is None or found[1] in pairs:raise ValueError('unrecognized named port')
        pairs[found[1]]=found[2]
    return pairs,opening,at+1


def stage_sources(output):
    output=Path(output)
    sources=[];frozen={}
    for name in OPERATORS:
        original=ROOT/'rtl'/f'main_heart_{name}.sv'
        body=original.read_text(encoding='utf-8')
        frozen[str(original)]=hashlib.sha256(original.read_bytes()).hexdigest()
        if name=='sqrt':
            # Joint timing showed a compare ->53-bit increment ->exponent
            # adjust chain. Keep integer-root and ties/rounding unchanged;
            # register each of the two rounding decisions before packing.
            changes=[
                ('ROOT,ROUND}', 'ROOT,ROUND_COMPARE,ROUND_INCREMENT,ROUND}'),
                ('    logic [53:0] rounded;',
                 '    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic [53:0] rounded;\n    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic round_up;'),
                ("        rounded={1'b0,root}+(remainder>{3'b0,root});\n", ''),
                ('count<=0;result_exponent<=0;rsp_valid<=0;',
                 'count<=0;result_exponent<=0;rounded<=0;round_up<=0;rsp_valid<=0;'),
                ('if(count==52) state<=ROUND;', 'if(count==52) state<=ROUND_COMPARE;'),
                ('            ROUND: begin', '''            ROUND_COMPARE:begin round_up<=remainder>{3'b0,root};state<=ROUND_INCREMENT;end
            ROUND_INCREMENT:begin rounded<={1'b0,root}+round_up;state<=ROUND;end
            ROUND: begin'''),
            ]
            for before,after in changes:
                if body.count(before)!=1:raise ValueError('sqrt rounding boundary changed: '+before)
                body=body.replace(before,after)
        if name!='sqrt':
            marker='history100_fp64 arithmetic('
            if body.count(marker)!=1:raise ValueError('expected one private arithmetic instance')
            start=body.index(marker);ports,_,end=call_ports(body,start)
            expected={'clk','reset_n','req_valid','req_ready','op','a','b','rsp_valid','rsp_ready','value','faults'}
            if set(ports)!=expected:raise ValueError('arithmetic port set changed')
            assignments=[]
            for wire in ('req_valid','op','a','b','rsp_ready'):
                assignments.append(f'    assign shared_{wire}={ports[wire]};')
            for wire in ('req_ready','rsp_valid','value','faults'):
                assignments.append(f'    assign {ports[wire]}=shared_{wire};')
            body=body[:start]+'\n'.join(assignments)+body[end:]
            header=body.index('\n);')
            extra=PORTS
            if name=='gain_argument':extra+=','+PORTS.replace('shared_','power_shared_')
            body=body[:header]+','+extra+body[header:]
        if name=='gain_argument':
            start=body.index('main_heart_pow2 power(')
            _,_,end=call_ports(body,start)
            connections=',\n'+','.join(f'.shared_{wire}(power_shared_{wire})' for wire in
                ('req_valid','req_ready','op','a','b','rsp_valid','rsp_ready','value','faults'))
            body=body[:end-2]+connections+body[end-2:]
            body=body.replace('main_heart_pow2 power(','main_shared_pow2 power(')
        body=body.replace(f'module main_heart_{name}',f'module main_shared_{name}',1)
        target=output/f'main_shared_{name}.sv'
        with target.open('x',encoding='utf-8') as stream:stream.write(body)
        sources.append(target)
    return sources,frozen


def wrapper(name):
    """Proof wrapper retaining the exact standalone test interface."""
    source=(ROOT/'rtl'/f'main_heart_{name}.sv').read_text(encoding='utf-8')
    declaration=source[:source.index('\n);')+4]
    common='.clk(clk),.reset_n(reset_n),.cancel(cancel),.req_valid(req_valid),.req_ready(req_ready),.rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.faults(faults)'
    extras={
        'log10':",.mode(3'd1),.a(argument),.b(64'b0),.value(value),.sample_flags(7'b0),.assessment_reason(8'b0),.input_valid(1'b0),.input_last(1'b0),.input_data(64'b0)",
        'welch':",.mode(3'd0),.a(64'b0),.b(64'b0),.value(band_power),.sample_flags(7'b0),.assessment_reason(8'b0),.input_valid(input_valid),.input_last(input_last),.input_data(input_data),.input_ready(input_ready)",
        'gain_argument':",.mode(3'd2),.a(original),.b(leakage),.value(value),.sample_flags(7'b0),.assessment_reason(8'b0),.input_valid(1'b0),.input_last(1'b0),.input_data(64'b0)",
        'fusion':",.mode(3'd3),.a(raw),.b(candidate),.value(value),.sample_flags({immediate_bypass,candidate_allowed,assessment_valid,clipped,contact_allowed,sample_reset,sample_valid}),.assessment_reason(assessment_reason),.input_valid(1'b0),.input_last(1'b0),.input_data(64'b0),"+','.join(f'.{p}({p})' for p in ('mix','index_out','good_out','cooldown_out','requested_out','history_count_out','reason','checked','protection'))
    }
    # Parameter declarations above remain accepted; generated ROM names are the
    # same defaults, and wrappers are proof-only (not synthesizable releases).
    return declaration+'\nmain_heart_shared_operators core('+common+extras[name]+');\nendmodule\n'


def write_fusion_vectors(output):
    proof=vectors();records=proof['records']
    with (output/'main_fusion_vectors.txt').open('x',encoding='ascii') as stream:
        stream.write(str(len(records))+'\n')
        for row in records:
            r,s=row['input'],row['state']
            flags=sum(int(r[name])<<bit for bit,name in enumerate(('valid','reset','contact','clipped','assessment_valid','allowed','immediate')))
            stream.write(f'{flags:x} {r["raw"]:016x} {r["candidate"]:016x} {r["assessment_reason"]:x} '
                f'{row["output"]:016x} {s["mix"]:016x} {s["index"]:x} {s["good"]:x} '
                f'{int(s["requested"]):x} {s["cooldown"] & 0xffffffff:08x} {s["history_count"]:x} '
                f'{s["reason"]:x} {int(s["protection"]):x} {int(row["checked"]):x}\n')


def run_rtl(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    derived,frozen=stage_sources(output)
    write_log_assets(output);write_gain_assets(output);write_welch_assets(output);write_fusion_vectors(output)
    fp=stage_arithmetic(output)
    core=(fp,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_mul53.sv',*derived,
          ROOT/'rtl/main_heart_fp64_arbiter.sv',ROOT/'rtl/main_heart_shared_operators.sv')
    expected={'log10':2299,'welch':578,'gain_argument':2290,'fusion':2407}
    results={}
    for name,count in expected.items():
        label='gain' if name=='gain_argument' else name
        w=output/f'wrapper_{name}.sv';tb=output/f'tb_shared_{name}.sv'
        with w.open('x',encoding='utf-8') as stream:stream.write(wrapper(name))
        test=(ROOT/'sim'/f'tb_main_heart_{label}.sv').read_text(encoding='utf-8')
        test=test.replace('dut.power.','dut.core.gain.power.').replace('dut.pc','dut.core.welch.pc')
        if name=='welch':
            test=test.replace('if(!input_ready) $fatal(1,"Welch input not ready");',
                'while(!input_ready) @(negedge clk);')
            # The shared parent locks a malformed transaction; reset between the
            # original independent invalid-input cases, not an implicit retry.
            test=test.replace('start();send_sample(64\'h3ff0000000000000,1);',
                'reset_n=0;@(negedge clk);reset_n=1;@(negedge clk);\n        start();send_sample(64\'h3ff0000000000000,1);')
            test=test.replace('f=$fopen("main_welch_vectors.txt","r");',
                'reset_n=0;@(negedge clk);reset_n=1;@(negedge clk);\n        f=$fopen("main_welch_vectors.txt","r");')
        if name=='log10':
            test=test.replace('checked=checked+1;',
                'checked=checked+1;\n            if(expected_fault!=0) begin reset_n=0;@(negedge clk);reset_n=1;@(negedge clk);end')
        if name=='fusion':
            test=test.replace('repeat(4) @(negedge clk);\n        if(!rsp_valid',
                'repeat(8) @(negedge clk);\n        if(!rsp_valid')
            # New parent must not accept requests into an error-locked child.
        with tb.open('x',encoding='utf-8') as stream:stream.write(test)
        sources=(*core,w,tb)
        directory=output/label;directory.mkdir(exist_ok=False)
        for asset in (*output.glob('*.mem'),*output.glob('*vectors.txt')):shutil.copy2(asset,directory/asset.name)
        compiled=compile_xsim(sources,f'tb_main_heart_{label}',directory)
        ran=run_tool('xsim',[f'tb_main_heart_{label}','--R','--log',str(directory/'native.log')],directory,timeout=600)
        found=re.findall(fr'MAIN_HEART_{label.upper()}_PASS checked=(\d+) max_cycles=(\d+) reset=1 cancel=1 stalls=1',ran['stdout'])
        if len(found)!=1 or int(found[0][0])!=count or source_hashes(sources)!=compiled['source_hashes']:
            raise ValueError('shared '+name+' proof incomplete')
        results[label]=dict(checked=count,max_cycles=int(found[0][1]),compile=compiled,simulation_log=ran['log'])
    unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==digest for p,digest in frozen.items())
    if not unchanged:raise ValueError('original operator source changed')
    result=dict(passed=True,arithmetic_instances=1,log_checked=2299,welch_checked=578,gain_checked=2290,
        fusion_checked=2407,differences=0,original_sources_unchanged=True,original_sources=frozen,
        operators=results,hardware_accessed=False,full_main_chain_verified=False,full_transaction_budget_passed=False)
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_synthesis(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    derived,frozen=stage_sources(output)
    write_log_assets(output);write_gain_assets(output);write_welch_assets(output)
    fp=stage_arithmetic(output);script=ROOT/'tcl/main_heart_shared_synth.tcl'
    sources=(fp,*derived,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_mul53.sv',ROOT/'rtl/main_heart_fp64_arbiter.sv',
             ROOT/'rtl/main_heart_shared_operators.sv',script)
    initial=source_hashes(sources)
    with (output/'initial-source-hashes.json').open('x',encoding='utf-8') as stream:json.dump(initial,stream,indent=2)
    ran=run_tool('vivado',['-mode','batch','-source',str(script),'-tclargs',str(output),str(ROOT)],output,timeout=900)
    if len(re.findall(r'(?m)^MAIN_HEART_SHARED_SYNTH_PASS arithmetic=1$',ran['stdout']))!=1 or source_hashes(sources)!=initial:
        raise ValueError('shared synthesis incomplete or source changed')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest for p,digest in frozen.items()):
        raise ValueError('original operator changed during synthesis')
    with (output/'resources.tsv').open('r',encoding='ascii') as stream:rows=list(csv.DictReader(stream,delimiter='\t'))
    if len(rows)!=1:raise ValueError('shared resource report incomplete')
    resources={k:int(v) for k,v in rows[0].items()}
    if resources.pop('arithmetic')!=1:raise ValueError('shared arithmetic duplicated')
    protected_input_bits=resources.pop('protected_input_bits')
    if protected_input_bits!=106:raise ValueError('multiply register boundary missing')
    normalization_bits=resources.pop('protected_normalization_bits')
    if normalization_bits!=6:raise ValueError('normalization register boundary missing')
    timing=(output/'synthesis-timing.rpt').read_text(encoding='utf-8')
    setup=re.search(r'Setup\s*:\s*\d+\s+Failing Endpoints,\s+Worst Slack\s+(-?[0-9.]+)ns',timing)
    hold=re.search(r'Hold\s*:\s*\d+\s+Failing Endpoints,\s+Worst Slack\s+(-?[0-9.]+)ns',timing)
    if setup is None or hold is None:raise ValueError('synthesis timing summary absent')
    wns,whs=float(setup[1]),float(hold[1])
    result=dict(synthesis_passed=True,arithmetic_instances=1,resources=resources,source_hashes=initial,
        protected_multiply_input_bits=protected_input_bits,
        protected_normalization_bits=normalization_bits,
        original_sources=frozen,hardware_accessed=False,joint_placement_timing_passed=False,
        isolated_setup_met=wns>=0,isolated_hold_met=whs>=0,isolated_wns_ns=wns,isolated_whs_ns=whs,
        full_transaction_budget_passed=False,tool_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_arbiter_rtl(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    fp=stage_arithmetic(output)
    sources=(fp,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_mul53.sv',ROOT/'rtl/main_heart_fp64_arbiter.sv',ROOT/'sim/tb_main_heart_arbiter.sv')
    compiled=compile_xsim(sources,'tb_main_heart_arbiter',output)
    ran=run_tool('xsim',['tb_main_heart_arbiter','--R','--log',str(output/'native.log')],output,timeout=120)
    found=re.findall(r'MAIN_HEART_ARBITER_PASS owners=(\d+) contention=1 cancel=1 stalls=1',ran['stdout'])
    if len(found)!=1 or int(found[0])!=8 or source_hashes(sources)!=compiled['source_hashes']:
        raise ValueError('shared arithmetic ownership proof incomplete')
    result=dict(passed=True,owners_checked=8,contention_checked=True,cancel_checked=True,
        backpressure_checked=True,hardware_accessed=False,compile=compiled,simulation_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_interleaved_rtl(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    derived,frozen=stage_sources(output)
    write_log_assets(output);write_gain_assets(output);write_welch_assets(output);write_fusion_vectors(output)
    fp=stage_arithmetic(output)
    test=(ROOT/'sim/tb_main_heart_fusion.sv').read_text(encoding='utf-8')
    test=test.replace('module tb_main_heart_fusion;','module tb_main_heart_interleaved;')
    connection='''logic [2:0] mode=3;
    integer math_count=0;
    main_heart_shared_operators dut(
        .clk(clk),.reset_n(reset_n),.cancel(cancel),.req_valid(req_valid),.req_ready(req_ready),
        .mode(mode),.a(raw),.b(candidate),
        .sample_flags({immediate_bypass,candidate_allowed,assessment_valid,clipped,contact_allowed,sample_reset,sample_valid}),
        .assessment_reason(assessment_reason),.input_valid(1'b0),.input_last(1'b0),.input_data(64'b0),
        .rsp_valid(rsp_valid),.rsp_ready(rsp_ready),.value(value),.mix(mix),.faults(faults),
        .index_out(index_out),.good_out(good_out),.cooldown_out(cooldown_out),.requested_out(requested_out),
        .history_count_out(history_count_out),.reason(reason),.checked(checked),.protection(protection));
    task automatic math_call(input logic [2:0] command,input logic [63:0] argument,expected);
        logic [255:0] snapshot;
        integer ticks;
        begin
            snapshot={mix,index_out,good_out,cooldown_out,requested_out,history_count_out,reason,checked,protection};
            if(!req_ready) $fatal(1,"interleaved not ready");
            mode=command;raw=argument;candidate=argument;req_valid=1;
            @(negedge clk);req_valid=0;ticks=0;
            while(!rsp_valid && ticks<16000) begin @(negedge clk);ticks=ticks+1;end
            if(!rsp_valid || value!==expected || faults!=0) $fatal(1,"interleaved math differs mode%d",command);
            if(snapshot!=={77'b0,mix,index_out,good_out,cooldown_out,requested_out,history_count_out,reason,checked,protection})
                $fatal(1,"math changed retained fusion state");
            repeat(3) @(negedge clk);
            rsp_ready=1;@(negedge clk);rsp_ready=0;mode=3;math_count=math_count+1;
        end
    endtask'''
    test=test.replace('main_heart_fusion dut(.*);',connection)
    test=test.replace('sample_valid=flags[0];',
        '''if(i%23==0) begin
                math_call(3'd1,64'h3ff0000000000000,64'b0);
                math_call(3'd2,64'h3ff0000000000000,64'h3ff0000000000000);
                math_call(3'd4,64'h4010000000000000,64'h4000000000000000);
            end
            sample_valid=flags[0];''')
    test=test.replace('repeat(4) @(negedge clk);\n        if(!rsp_valid',
        'repeat(8) @(negedge clk);\n        if(!rsp_valid')
    test=test.replace('$display("MAIN_HEART_FUSION_PASS',
        '$display("MAIN_HEART_INTERLEAVED_MATH calls=%0d",math_count);\n        $display("MAIN_HEART_FUSION_PASS')
    tb=output/'tb_main_heart_interleaved.sv'
    with tb.open('x',encoding='utf-8') as stream:stream.write(test)
    sources=(fp,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_mul53.sv',*derived,
        ROOT/'rtl/main_heart_fp64_arbiter.sv',ROOT/'rtl/main_heart_shared_operators.sv',tb)
    compiled=compile_xsim(sources,'tb_main_heart_interleaved',output)
    ran=run_tool('xsim',['tb_main_heart_interleaved','--R','--log',str(output/'native.log')],output,timeout=300)
    if ('MAIN_HEART_FUSION_PASS checked=2407 ' not in ran['stdout'] or
        'MAIN_HEART_INTERLEAVED_MATH calls=315' not in ran['stdout'] or source_hashes(sources)!=compiled['source_hashes']):
        raise ValueError('mixed internal operator state proof incomplete')
    if any(hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest for p,digest in frozen.items()):
        raise ValueError('mixed operator source changed')
    result=dict(passed=True,fusion_steps=2407,internal_math_calls=315,differences=0,
        fusion_state_retained=True,hardware_accessed=False,compile=compiled,simulation_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_route(output,synthesis):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    synthesis=Path(synthesis).resolve()
    proof=json.loads((synthesis/'result.json').read_bytes())
    if not proof['synthesis_passed'] or proof['arithmetic_instances']!=1:raise ValueError('bad synthesis evidence')
    for p,digest in proof['source_hashes'].items():
        if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=digest:raise ValueError('synthesis source changed')
    checkpoint=synthesis/'main_heart_shared_operators.dcp';script=ROOT/'tcl/main_heart_shared_route.tcl'
    initial=source_hashes((checkpoint,script,synthesis/'result.json'))
    with (output/'initial-source-hashes.json').open('x',encoding='utf-8') as stream:json.dump(initial,stream,indent=2)
    ran=run_tool('vivado',['-mode','batch','-source',str(script),'-tclargs',str(output),str(checkpoint)],output,timeout=1800)
    if len(re.findall(r'(?m)^MAIN_HEART_SHARED_ROUTE_FINISHED$',ran['stdout']))!=1 or source_hashes(initial)!=initial:
        raise ValueError('isolated route incomplete or input changed')
    with (output/'timing.tsv').open('r',encoding='ascii') as stream:rows=list(csv.DictReader(stream,delimiter='\t'))
    if len(rows)!=1 or float(rows[0]['period_ns'])!=10.:raise ValueError('routed100MHz timing missing')
    wns,whs=float(rows[0]['wns_ns']),float(rows[0]['whs_ns'])
    result=dict(isolated_route_finished=True,isolated_routed_setup_met=wns>=0,isolated_routed_hold_met=whs>=0,
        isolated_wns_ns=wns,isolated_whs_ns=whs,clock_hz=100_000_000,source_hashes=initial,
        joint_placement_timing_passed=False,full_transaction_budget_passed=False,hardware_accessed=False,
        interface_delays_or_joint_cdc_checked=False,tool_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_buffered_multiply(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    values={0,1,2,3,(1<<53)-1}
    for k in range(53):values.update({1<<k,(1<<k)-1,min((1<<53)-1,(1<<k)+1)})
    pairs=[(a,b) for a in sorted(values) for b in sorted(values)]
    rng=random.Random(251017);pairs.extend((rng.getrandbits(53),rng.getrandbits(53)) for _ in range(10000))
    with (output/'multiply.txt').open('x',encoding='ascii') as stream:
        for a,b in pairs:stream.write(f'{a:014x} {b:014x} {a*b:027x}\n')
    test=(ROOT/'sim/tb_history100_mul53.sv').read_text(encoding='utf-8')
    test=test.replace('history100_mul53 dut','main_heart_mul53 dut').replace('phase<12','phase<14').replace('reset_phases=12','reset_phases=14')
    tb=output/'tb_main_heart_buffered_multiply.sv'
    with tb.open('x',encoding='utf-8') as stream:stream.write(test)
    sources=(ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_mul53.sv',tb)
    compiled=compile_xsim(sources,'tb_history100_mul53',output)
    ran=run_tool('xsim',['tb_history100_mul53','--R','--log',str(output/'native.log')],output,timeout=180)
    found=re.findall(r'HISTORY100_MUL53_PASS checked=(\d+) max_cycles=(\d+) reset_phases=14 stalls=1',ran['stdout'])
    if len(found)!=1 or int(found[0][0])!=len(pairs) or source_hashes(sources)!=compiled['source_hashes']:
        raise ValueError('private buffered exact multiply proof incomplete')
    result=dict(passed=True,checked=len(pairs),max_cycles=int(found[0][1]),reset_phases=14,
        compile=compiled,simulation_log=ran['log'],hardware_accessed=False)
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_normalized_arithmetic(output):
    from .small_heart_rtl import arithmetic_vectors
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    frozen=source_hashes((ROOT/'rtl/history100_fp64.sv',ROOT/'rtl/history100_mul53.sv'))
    fp=stage_arithmetic(output);vectors=list(arithmetic_vectors())
    for bit in range(52):
        # Literal powers of two, independently derived IEEE expectations.
        vectors.extend(((0,1<<bit,1<<bit,1<<(bit+1),0),
                        (2,1<<bit,0x3ff0000000000000,1<<bit,0),
                        (3,1<<bit,0x3ff0000000000000,1<<bit,0)))
    with (output/'fp64.txt').open('x',encoding='ascii') as stream:
        for op,a,b,value,fault in vectors:stream.write(f'{op} {a:016x} {b:016x} {value:016x} {fault:x}\n')
    sources=(fp,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_mul53.sv',ROOT/'sim/tb_main_heart_normalization.sv')
    compiled=compile_xsim(sources,'tb_main_heart_normalization',output)
    ran=run_tool('xsim',['tb_main_heart_normalization','--R','--log',str(output/'native.log')],output,timeout=180)
    pattern=r'MAIN_HEART_NORMALIZATION_PASS checked=(\d+) max_by_op=(\d+),(\d+),(\d+),(\d+) split_a=1 split_b=1 reset_phases=18 stalls=1'
    found=re.findall(pattern,ran['stdout'])
    if len(found)!=1 or int(found[0][0])!=len(vectors) or source_hashes(sources)!=compiled['source_hashes']:
        raise ValueError('split normalization arithmetic proof incomplete')
    if source_hashes(frozen)!=frozen:raise ValueError('original arithmetic changed')
    result=dict(passed=True,checked=len(vectors),max_cycles_by_op=list(map(int,found[0][1:])),
        split_a_checked=True,split_b_checked=True,reset_phases=18,backpressure_checked=True,
        original_sources_unchanged=True,original_sources=frozen,hardware_accessed=False,
        compile=compiled,simulation_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_normalized_history(output):
    """Recheck the existing causal history unit with the SAME private FP64.

    This is a component simulation, not the unfinished whole sample transaction.
    The original history generator, reference archive and successful RTL stay
    unchanged; only a private source set is compiled in this new directory.
    """
    from .history100_dsp import candidate_sources
    from .history100_online_rtl import _online_vectors
    from .history100_rtl import cases
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    frozen=source_hashes(tuple(ROOT/'rtl'/name for name in (
        'history100_fp64.sv','history100_mul53.sv','history100_online_engine.sv',
        'history100_sha256.sv','history100_online.sv','history100_online_axi.sv')))
    old=candidate_sources(output/'history_sources')
    private=output/'arithmetic';private.mkdir(exist_ok=False)
    fp=stage_arithmetic(private)
    count=_online_vectors(output)
    sources=(fp,*old[1:],ROOT/'rtl/main_heart_mul53.sv',ROOT/'sim/tb_history100_online_axi.sv')
    compiled=compile_xsim(sources,'tb_history100_online_axi',output)
    ran=run_tool('xsim',['tb_history100_online_axi','--R','--log',str(output/'native.log')],output,timeout=1800)
    pattern=r'HISTORY100_ONLINE_AXI_PASS steps=(\d+) windows=(\d+) words=(\d+) max_cycles=(\d+) bus=(\d+) stop=1'
    found=re.findall(pattern,ran['stdout'])
    if len(found)!=1 or source_hashes(sources)!=compiled['source_hashes']:raise ValueError('normalized history proof incomplete')
    steps,windows,words,cycles,bus=map(int,found[0])
    if (steps,windows,words)!=(count,287,59983):raise ValueError('normalized history coverage differs')
    actual=(output/'axi-observed.txt').read_text(encoding='ascii').splitlines()
    if len(actual)!=287*210:raise ValueError('normalized history physical dump incomplete')
    for ci,row in enumerate(cases()):
        if actual[ci*210].split()!=['digest',str(ci),hashlib.sha256(bytes.fromhex(row['inputs'])).hexdigest()]:
            raise ValueError('normalized history input identity differs')
        expected=bytes.fromhex(row['squares']+row['numerators'])
        for wi in range(209):
            if actual[ci*210+1+wi].split()!=['word',str(ci),str(wi),expected[wi*8:wi*8+8][::-1].hex()]:
                raise ValueError('normalized history ARM word differs')
    if source_hashes(frozen)!=frozen:raise ValueError('original history sources changed')
    result=dict(passed=True,schema='main_heart_normalized_history_component_v1',saved_rows=1504,
        invalid_sequences=[1],steps=steps,windows=windows,real_windows=281,boundary_windows=6,
        primitive_words_checked=words,differences=0,max_busy_cycles=cycles,bus_checks=bus,
        original_sources_unchanged=True,original_sources=frozen,stop_checked=True,
        fixture_sha256=hashlib.sha256((output/'online.txt').read_bytes()).hexdigest(),
        actual_dump_sha256=hashlib.sha256((output/'axi-observed.txt').read_bytes()).hexdigest(),
        hardware_accessed=False,full_transaction_budget_passed=False,compile=compiled,simulation_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result
