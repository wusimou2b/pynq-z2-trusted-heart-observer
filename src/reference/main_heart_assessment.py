"""Compile complete frozen history assessment to a PL-internal program.

The reference is the saved ARM archive. This interpreter is a compiler check,
not an ARM substitute, not a hardware backend and not an authorization gate.
No thresholds, reductions, FFT factorization or libm operations are changed.
"""
from functools import lru_cache
import json
from pathlib import Path
import struct
import re

from .main_heart_operators import arm_cases, word, number, log10_word, arm_pow2
from .main_heart_reference import load_cases, sqrt_bits
from .main_heart_welch import welch100
from .main_heart_fusion import REASONS

ROOT = Path(__file__).resolve().parent
SQUARES, NUMERATORS, NORMS, MAXIMA = 700, 777, 909, 986
ENERGY, POWER, OUTPUT, TEMP, CONSTANTS = 1006, 1013, 1100, 1200, 1856
OPS = dict(done=0, mov=1, absolute=2, finite=3, bitand=4, bitor=5,
           add=16, sub=17, mul=18, div=19, sqrt=20, gain=21, log=22,
           welch=23, jz=32, jnz=33, flt=34, fge=35, jump=36)


class Program:
    def __init__(self):
        self.code, self.constants, self.labels, self.fixups = [], [], {}, []

    def constant(self, value, *, integer=False):
        value = int(value) if integer else word(value)
        if value not in self.constants:
            self.constants.append(value)
        return CONSTANTS + self.constants.index(value)

    def label(self, name):
        if name in self.labels:
            raise ValueError('duplicate assessment label')
        self.labels[name] = len(self.code)

    def emit(self, name, d=0, a=0, b=0, target=0):
        if isinstance(target, str):
            self.fixups.append((len(self.code), target))
            target = 0
        self.code.append([OPS[name], d, a, b, target])

    def finish(self):
        for index, name in self.fixups:
            self.code[index][4] = self.labels[name]
        if len(self.code) > 4096 or CONSTANTS + len(self.constants) > 2048:
            raise ValueError('assessment program/data capacity exceeded')
        return self


@lru_cache(maxsize=1)
def compile_program():
    p = Program()
    z, one, eps, rms_min, power_min, neg_eps, ten, hundred = [
        p.constant(x) for x in (0., 1., 1e-12, .4, .5, -1e-12, 10., 100.)]
    iz, i1, i2, i3 = [p.constant(x, integer=True) for x in (0, 1, 2, 3)]
    nan = p.constant(0x7ff8000000000000, integer=True)
    t = list(range(TEMP, TEMP + 32))
    # refs**2 is a C100x4 array: NumPy axis0 adds sequentially per column.
    # raw/candidate/actual**2 are contiguous vectors: original8-lane reduction.
    for ch in range(7):
        if ch >= 3:
            p.emit('mov', ENERGY + ch, z)
            for i in range(100):
                p.emit('mul', t[0], ch*100+i, ch*100+i)
                p.emit('add', ENERGY + ch, ENERGY + ch, t[0])
        else:
            for i in range(8):
                p.emit('mul', t[i], ch*100+i, ch*100+i)
            for i in range(8, 96):
                p.emit('mul', t[8], ch*100+i, ch*100+i)
                p.emit('add', t[i % 8], t[i % 8], t[8])
            for dest, a, b in ((0,0,1),(1,2,3),(2,4,5),(3,6,7),(0,0,1),(1,2,3),(0,0,1)):
                p.emit('add', t[dest], t[a], t[b])
            for i in range(96, 100):
                p.emit('mul', t[8], ch*100+i, ch*100+i)
                p.emit('add', t[0], t[0], t[8])
            p.emit('add', ENERGY + ch, z, t[0])
        p.emit('div', ENERGY + ch, ENERGY + ch, hundred)
    # Norms, opposite lag pairing and conditional division before max(abs).
    for i in range(77):
        p.emit('sqrt', NORMS+i, SQUARES+i)
    for pair in range(12):
        p.emit('mov', MAXIMA+pair, z)
        for lag in range(11):
            end = f'score_{pair}_{lag}'
            p.emit('mul', t[0], NORMS+(pair//4)*11+lag,
                   NORMS+(3+pair%4)*11+10-lag)
            p.emit('jz', a=t[0], target=end)
            p.emit('div', t[1], NUMERATORS+pair*11+lag, t[0])
            p.emit('absolute', t[1], t[1])
            p.emit('fge', a=MAXIMA+pair, b=t[1], target=end)
            p.emit('mov', MAXIMA+pair, t[1])
            p.label(end)
    # Output0..7 gains,8..11 energies,12..15 ratios,16active,17finite,
    #18allowed,19immediate,20reason. Non-required gains remain original qNaN.
    for i in range(8):
        p.emit('mov', OUTPUT+i, nan)
    p.emit('mov', OUTPUT+16, iz)
    for j in range(4):
        skip = f'inactive_{j}'
        if j:
            p.emit('fge', a=eps, b=ENERGY+3+j, target=skip)
            mask = p.constant(1 << (j-1), integer=True)
            p.emit('bitor', OUTPUT+16, OUTPUT+16, mask)
        for signal in (1, 2):
            p.emit('gain', t[0], MAXIMA+j, MAXIMA+signal*4+j)
            p.emit('log', t[0], t[0])
            p.emit('mul', OUTPUT+(signal-1)*4+j, ten, t[0])
        p.label(skip)
        p.emit('mov', OUTPUT+8+j, ENERGY+3+j)
    for ch in range(3):
        p.emit('welch', POWER+ch, ch*100)
    p.emit('sqrt', t[10], ENERGY)
    p.emit('fge', a=t[10], b=eps, target='raw_rms_ok')
    p.emit('mov', t[10], eps)
    p.label('raw_rms_ok')
    p.emit('mov', t[11], POWER)
    p.emit('fge', a=t[11], b=eps, target='raw_power_ok')
    p.emit('mov', t[11], eps)
    p.label('raw_power_ok')
    for ch in (1, 2):
        dst = OUTPUT+12+(ch-1)*2
        p.emit('sqrt', t[0], ENERGY+ch)
        p.emit('div', dst, t[0], t[10])
        p.emit('div', dst+1, POWER+ch, t[11])
    for branch in range(2):
        p.emit('mov', t[12+branch], i1)
        for address in (OUTPUT+12+branch*2, OUTPUT+13+branch*2, *range(OUTPUT+branch*4, OUTPUT+branch*4+4)):
            j = address - (OUTPUT+branch*4)
            label = f'finite_skip_{branch}_{address}'
            if 1 <= j <= 3:
                p.emit('fge', a=eps, b=ENERGY+3+j, target=label)
            p.emit('finite', t[0], address)
            p.emit('bitand', t[12+branch], t[12+branch], t[0])
            p.label(label)
    p.emit('mov', OUTPUT+17, t[12])
    p.emit('jz', a=t[13], target='finite_done')
    p.emit('bitor', OUTPUT+17, OUTPUT+17, i2)
    p.label('finite_done')
    p.emit('mov', OUTPUT+18, iz)
    p.emit('mov', OUTPUT+19, iz)
    p.emit('jz', a=t[13], target='actual_amplitude_power_protection')
    p.emit('flt', a=OUTPUT+14, b=rms_min, target='actual_amplitude_power_protection')
    p.emit('flt', a=OUTPUT+15, b=power_min, target='actual_amplitude_power_protection')
    for offset, name in ((4, 'actual_gain_protection'), (0, 'candidate_axis_worsening')):
        if offset == 0:
            p.emit('fge', a=eps, b=ENERGY, target='degenerate_reference_or_ppg')
            p.emit('fge', a=eps, b=ENERGY+3, target='degenerate_reference_or_ppg')
            p.emit('jz', a=OUTPUT+16, target='no_active_axes')
            p.emit('jz', a=t[12], target='nonfinite_candidate')
            p.emit('flt', a=OUTPUT+12, b=rms_min, target='poor_rms')
            p.emit('flt', a=OUTPUT+13, b=power_min, target='poor_power')
            p.emit('flt', a=OUTPUT, b=one, target='insufficient_magnitude_benefit')
        for j in range(0 if offset else 1, 4):
            end = f'decision_skip_{offset}_{j}'
            if j:
                p.emit('fge', a=eps, b=ENERGY+3+j, target=end)
            p.emit('flt', a=OUTPUT+offset+j, b=neg_eps, target=name)
            p.label(end)
    p.emit('jump', target='benefit_confirmed')
    for reason in REASONS[3:13]:
        p.label(reason)
        p.emit('mov', OUTPUT+20, p.constant(REASONS.index(reason), integer=True))
        if reason.startswith('actual_'):
            p.emit('mov', OUTPUT+19, i1)
        if reason == 'benefit_confirmed':
            p.emit('mov', OUTPUT+18, i1)
        p.emit('done')
    return p.finish()


def initial_memory(row):
    memory = [0]*2048
    for base, field in ((0, 'inputs'), (SQUARES, 'squares'), (NUMERATORS, 'numerators')):
        data = bytes.fromhex(row[field])
        values = struct.unpack('<'+'Q'*(len(data)//8), data)
        memory[base:base+len(values)] = values
    p = compile_program()
    memory[CONSTANTS:CONSTANTS+len(p.constants)] = p.constants
    return memory


def execute(row):
    memory = initial_memory(row)
    code, pc, steps = compile_program().code, 0, 0
    while True:
        op, dst, a, b, target = code[pc]
        x, y = memory[a], memory[b]
        xf, yf = number(x), number(y)
        pc += 1
        steps += 1
        if steps > 4096:
            raise ValueError('assessment control did not terminate')
        if op == OPS['done']:
            break
        if op == OPS['mov']: value = x
        elif op == OPS['absolute']: value = x & ((1 << 63)-1)
        elif op == OPS['finite']: value = int((x >> 52) & 2047 != 2047)
        elif op == OPS['bitand']: value = x & y
        elif op == OPS['bitor']: value = x | y
        elif op in (16, 17, 18, 19):
            value = word(xf+yf if op == 16 else xf-yf if op == 17 else xf*yf if op == 18 else xf/yf)
        elif op == OPS['sqrt']: value = sqrt_bits(x)
        elif op == OPS['gain']: value = word((arm_pow2(xf)+1e-12)/(arm_pow2(yf)+1e-12))
        elif op == OPS['log']: value = log10_word(x)
        elif op == OPS['welch']:
            value = word(welch100([number(v) for v in memory[a:a+100]])[0])
        elif op in (32, 33, 34, 35, 36):
            condition = (x == 0 if op == 32 else x != 0 if op == 33 else
                         xf < yf if op == 34 else xf >= yf if op == 35 else True)
            if condition: pc = target
            continue
        else: raise ValueError('unknown assessment opcode')
        memory[dst] = value
    return memory[OUTPUT:OUTPUT+21], steps


def expected_words(observed):
    result = []
    for key in ('candidate_gains', 'actual_gains', 'reference_energy'):
        data = bytes.fromhex(observed[key][2])
        result.extend(struct.unpack('<4Q', data))
    result.extend(int(observed[k], 16) for k in (
        'candidate_rms_ratio', 'candidate_power_ratio', 'actual_rms_ratio', 'actual_power_ratio'))
    active = bytes.fromhex(observed['active_axes'][2])
    result.extend((sum(int(v) << i for i, v in enumerate(active)),
        int(observed['candidate_finite']) | int(observed['actual_finite']) << 1,
        int(observed['candidate_allowed']), int(observed['immediate_bypass']), REASONS.index(observed['reason'])))
    return result


def qualify_program():
    actual, observed = load_cases(), arm_cases()
    if len(actual) != 287 or len(observed) != 287:
        raise ValueError('assessment references incomplete')
    for i, (row, saved) in enumerate(zip(actual, observed)):
        got, _ = execute(row)
        expected = expected_words(saved['assessment'])
        wrong = [j for j, (a, b) in enumerate(zip(got, expected)) if a != b]
        if wrong:
            raise ValueError(f'complete ARM assessment differs case{i} words{wrong}: '
                             + str([(j, f'{got[j]:016x}', f'{expected[j]:016x}') for j in wrong[:5]]))
    return dict(windows=287, real_windows=281, assessment_words_checked=6027,
        word_differences=0, decision_differences=0, program_instructions=len(compile_program().code),
        hardware_accessed=False, rtl_verified=False)


def write_assets(output, *, primitives=True):
    output = Path(output)
    p = compile_program()
    encoded = [(op << 88) | (d << 77) | (a << 66) | (b << 55) | (target << 43)
               for op, d, a, b, target in p.code]
    with (output/'main_assessment_program.mem').open('x', encoding='ascii') as stream:
        stream.write(''.join(f'{v:024x}\n' for v in encoded + [0]*(4096-len(encoded))))
    initial = [0]*2048
    initial[CONSTANTS:CONSTANTS+len(p.constants)] = p.constants
    with (output/'main_assessment_initial.mem').open('x', encoding='ascii') as stream:
        stream.write(''.join(f'{v:016x}\n' for v in initial))
    with (output/'main_assessment_vectors.txt').open('x', encoding='ascii') as stream:
        stream.write('287\n')
        for row, observed in zip(load_cases(), arm_cases()):
            values = initial_memory(row)[:909 if primitives else 700] + expected_words(observed['assessment'])
            stream.write(''.join(f'{v:016x}\n' for v in values))


def stage_math(output):
    """Private8-client hub: operators, assessment, internal history and BANK.

    This is generation from pinned, already-tested shared wiring, not a new
    PS-visible operator protocol. Original operator files stay unchanged.
    """
    from .main_heart_shared import PORTS
    body = (ROOT/'rtl/main_heart_shared_operators.sv').read_text('utf-8')
    extra = '\n    input logic [1:0] operation,\n'
    for prefix in ('history_', 'bank_'):
        extra += PORTS.replace('shared_', prefix).replace('output logic', 'TEMP_DIRECTION')\
            .replace('input logic', 'output logic').replace('TEMP_DIRECTION', 'input logic') + ',\n'
    extra = extra.rstrip(',\n')
    changes = [
        ('module main_heart_shared_operators(', 'module main_heart_math('),
        ('    output logic checked,protection\n);', '    output logic checked,protection,' + extra + '\n);'),
        ('logic [2:0] active;', 'logic [2:0] active;\n    logic [1:0] held_operation;'),
        ('logic [4:0] child_req,child_ready,child_valid,child_ack;', 'logic [5:0] child_req,child_ready,child_valid,child_ack;'),
        ('logic [4:0][63:0] child_value;', 'logic [5:0][63:0] child_value;'),
        ('logic [4:0][3:0] child_faults;', 'logic [5:0][3:0] child_faults;'),
        ('logic [4:0] fp_req,fp_ready,fp_valid,fp_ack;', 'logic [7:0] fp_req,fp_ready,fp_valid,fp_ack;'),
        ('logic [4:0][1:0] fp_op;', 'logic [7:0][1:0] fp_op;'),
        ('logic [4:0][63:0] fp_a,fp_b,fp_value;', 'logic [7:0][63:0] fp_a,fp_b,fp_value;'),
        ('logic [4:0][3:0] fp_faults;', 'logic [7:0][3:0] fp_faults;'),
        ('flags<=0;ar<=0;end', 'flags<=0;ar<=0;held_operation<=0;end'),
        ('active<=mode;aa<=a;bb<=b;flags<=sample_flags;ar<=assessment_reason;',
         'active<=mode;aa<=a;bb<=b;flags<=sample_flags;ar<=assessment_reason;held_operation<=operation;'),
        ('state<=mode<=4 ? LAUNCH : ERROR;', 'state<=mode<=5 ? LAUNCH : ERROR;'),
        ('main_heart_fp64_arbiter arithmetic_owner(', 'main_heart_fp64_arbiter #(.CLIENTS(8)) arithmetic_owner('),
    ]
    for before, after in changes:
        if body.count(before) != 1:
            raise ValueError('math hub derivation anchor changed: ' + before)
        body = body.replace(before, after)
    # The outer controller masks replies/acceptance on the original cycle.
    # Only physical child cancellation is distributed through a registered
    # boundary, avoiding a watchdog->nested fault mux->register-CE path.
    # No math operation, transaction deadline or public state changes.
    body=body.replace('    logic welch_ready;', '''    logic welch_ready;
    (* KEEP="TRUE", DONT_TOUCH="TRUE" *) logic [5:0] child_cancel;
    always_ff @(posedge clk) begin
        if(!reset_n) child_cancel<='1;
        else child_cancel<={6{cancel}};
    end''')
    names=('main_shared_welch welch(', 'main_shared_log10 logarithm(',
           'main_shared_gain_argument gain(', 'main_shared_fusion fusion(',
           'main_shared_sqrt square_root(', 'main_heart_fp64_arbiter #(.CLIENTS(8)) arithmetic_owner(')
    for i,name in enumerate(names):
        begin=body.index(name);end=body.index(');',begin)+2
        old=body[begin:end]
        if old.count('.cancel(cancel)')!=1:raise ValueError('cancel boundary anchor changed: '+name)
        body=body[:begin]+old.replace('.cancel(cancel)',f'.cancel(child_cancel[{i}])')+body[end:]
    wiring = '''
    assign fp_req[5]=child_req[5];assign child_ready[5]=fp_ready[5];
    assign child_valid[5]=fp_valid[5];assign fp_ack[5]=child_ack[5];
    assign fp_op[5]=held_operation;assign fp_a[5]=aa;assign fp_b[5]=bb;
    assign child_value[5]=fp_value[5];assign child_faults[5]=fp_faults[5];
'''
    for i, prefix in ((6, 'history_'), (7, 'bank_')):
        for direction, name, bus in (
            ('in','req_valid','fp_req'), ('out','req_ready','fp_ready'),
            ('in','op','fp_op'), ('in','a','fp_a'), ('in','b','fp_b'),
            ('out','rsp_valid','fp_valid'), ('in','rsp_ready','fp_ack'),
            ('out','value','fp_value'), ('out','faults','fp_faults')):
            lhs, rhs = (f'{bus}[{i}]', prefix+name) if direction == 'in' else (prefix+name, f'{bus}[{i}]')
            wiring += f'    assign {lhs}={rhs};\n'
    body = body.replace('endmodule', wiring+'endmodule')
    target = Path(output)/'main_heart_math.sv'
    with target.open('x', encoding='utf-8') as stream: stream.write(body)
    return target


def run_rtl(output):
    from .main_heart_shared import stage_arithmetic
    from .main_heart_log_registers import stage_components
    from .main_heart_operators import write_log_assets, write_gain_assets
    from .main_heart_welch import write_welch_assets
    from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim, run_tool, source_hashes
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    proof = qualify_program()
    derived, frozen = stage_components(output)
    fp = stage_arithmetic(output)
    write_assets(output)
    write_log_assets(output); write_gain_assets(output); write_welch_assets(output)
    hub = stage_math(output)
    sources = (fp, *derived, ROOT/'rtl/history100_mul53.sv', ROOT/'rtl/main_heart_mul53.sv',
        ROOT/'rtl/main_heart_fp64_arbiter.sv', hub, ROOT/'rtl/main_heart_assessment.sv',
        ROOT/'sim/tb_main_heart_assessment.sv')
    compiled = compile_xsim(sources, 'tb_main_heart_assessment', output)
    ran = run_tool('xsim', ['tb_main_heart_assessment', '--R', '--log', str(output/'native.log')], output, timeout=600)
    found = re.findall(r'MAIN_HEART_ASSESSMENT_PASS windows=(\d+) words=(\d+) max_cycles=(\d+) reset=1 cancel=1 stalls=1 malformed=1', ran['stdout'])
    if len(found) != 1 or list(map(int, found[0][:2])) != [287, 6027] or source_hashes(sources) != compiled['source_hashes']:
        raise ValueError('assessment RTL proof incomplete or changed')
    result = dict(proof, passed=True, max_cycles=int(found[0][2]), reset_checked=True,
        cancel_checked=True, backpressure_checked=True, malformed_checked=True,
        compile=compiled, simulation_log=ran['log'], original_sources=frozen,
        full_main_chain_verified=False, full_transaction_budget_passed=False)
    result['rtl_verified'] = True
    with (output/'result.json').open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2)
    return result


def stage_history(output):
    from .main_heart_shared import PORTS, call_ports
    original = ROOT/'rtl/history100_engine.sv'
    body = original.read_text('utf-8')
    start = body.index('history100_fp64 arithmetic(')
    ports, _, end = call_ports(body, start)
    wiring = []
    for name in ('req_valid', 'op', 'a', 'b', 'rsp_ready'):
        wiring.append(f'    assign shared_{name}={ports[name]};')
    for name in ('req_ready', 'rsp_valid', 'value', 'faults'):
        wiring.append(f'    assign {ports[name]}=shared_{name};')
    body = body[:start]+'\n'.join(wiring)+body[end:]
    at = body.index('\n);')
    body = body[:at]+','+PORTS+body[at:]
    body = body.replace('module history100_engine', 'module main_shared_history', 1)
    # Compute each window's bases once before reading it. The original engine
    # remains untouched; no index->multiply->BRAM address chain is repeated
    # per arithmetic element in this private continuous-chain derivative.
    changes=[
        ('DREDUCE,DTAIL_READ,DTAIL_GET,DZERO,ISSUE,WAIT_FP,STORE}',
         'DREDUCE,DTAIL_READ,DTAIL_GET,DZERO,ISSUE,WAIT_FP,STORE,ADDRESS_PARTS,ADDRESS_BASES}'),
        ('    wire [12:0] base_a=(cross_mode ? (pair_index/4)*11+lag_index : part_index)*100;\n    wire [12:0] base_b=(cross_mode ? (3+pair_index%4)*11+(10-lag_index) : part_index)*100;',
         '''    logic [6:0] address_part_a,address_part_b;
    logic [9:0] channel_base,window_base;
    logic [12:0] base_a,base_b;'''),
        ('wa=channel*100+(lag_index>5 ? lag_index-5 : 0)+element;', 'wa=window_base+element;'),
        ('tree<=0;cross_mode<=0;mean_value<=0;',
         'tree<=0;cross_mode<=0;address_part_a<=0;address_part_b<=0;channel_base<=0;window_base<=0;base_a<=0;base_b<=0;mean_value<=0;'),
        ('cross_mode<=0;state<=SREAD;', 'cross_mode<=0;state<=ADDRESS_PARTS;'),
        ('            SREAD:state<=SGET;', '''            ADDRESS_PARTS:begin
                address_part_a<=cross_mode ? (pair_index/4)*11+lag_index : part_index;
                address_part_b<=cross_mode ? (3+pair_index%4)*11+(10-lag_index) : part_index;
                channel_base<=channel*10'd100;state<=ADDRESS_BASES;
            end
            ADDRESS_BASES:begin
                base_a<=address_part_a*13'd100;base_b<=address_part_b*13'd100;
                window_base<=channel_base+(lag_index>5 ? lag_index-5 : 0);
                state<=cross_mode ? DOT_INIT : SREAD;
            end
            SREAD:state<=SGET;'''),
        ('if(lag_index<10) begin lag_index<=lag_index+1;length<=part_length(lag_index+1);state<=SREAD;end',
         'if(lag_index<10) begin lag_index<=lag_index+1;length<=part_length(lag_index+1);state<=ADDRESS_PARTS;end'),
        ('else if(channel<6) begin channel<=channel+1;lag_index<=0;length<=95;state<=SREAD;end',
         'else if(channel<6) begin channel<=channel+1;lag_index<=0;length<=95;state<=ADDRESS_PARTS;end'),
        ('else begin cross_mode<=1;pair_index<=0;lag_index<=0;length<=95;state<=DOT_INIT;end',
         'else begin cross_mode<=1;pair_index<=0;lag_index<=0;length<=95;state<=ADDRESS_PARTS;end'),
        ('if(lag_index<10) begin lag_index<=lag_index+1;length<=part_length(lag_index+1);state<=DOT_INIT;end',
         'if(lag_index<10) begin lag_index<=lag_index+1;length<=part_length(lag_index+1);state<=ADDRESS_PARTS;end'),
        ('else if(pair_index<11) begin pair_index<=pair_index+1;lag_index<=0;length<=95;state<=DOT_INIT;end',
         'else if(pair_index<11) begin pair_index<=pair_index+1;lag_index<=0;length<=95;state<=ADDRESS_PARTS;end'),
    ]
    for before,after in changes:
        if body.count(before)!=1:raise ValueError('registered history address anchor changed: '+before)
        body=body.replace(before,after)
    target = Path(output)/'main_shared_history.sv'
    with target.open('x', encoding='utf-8') as stream: stream.write(body)
    return target


def run_history_rtl(output, *, fast_arithmetic=False):
    from .main_heart_history_timing import stage as stage_window
    from .main_heart_shared import stage_arithmetic
    from .main_heart_log_registers import stage_components
    from .main_heart_operators import write_log_assets, write_gain_assets
    from .main_heart_welch import write_welch_assets
    from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim, run_tool, source_hashes
    output = Path(output).resolve();output.mkdir(parents=True, exist_ok=False)
    derived, frozen = stage_components(output)
    if fast_arithmetic:
        from .main_heart_fast import stage as make_arithmetic
    else:
        make_arithmetic=stage_arithmetic
    fp = make_arithmetic(output); hub = stage_math(output); history = stage_history(output)
    write_assets(output, primitives=False)
    write_log_assets(output);write_gain_assets(output);write_welch_assets(output)
    test = (ROOT/'sim/tb_main_heart_assessment.sv').read_text('utf-8')
    test = test.replace('module tb_main_heart_assessment;', 'module tb_main_heart_history_assessment;')
    test = test.replace('main_heart_assessment dut(', 'main_heart_history_window dut(')
    test = test.replace('dut.pc', 'dut.assessor.pc')
    test = test.replace('inputs[0:908]', 'inputs[0:699]').replace('i<909', 'i<700')
    # The full primitive engine reports malformed loading as its own locked
    # fault; the isolated assessor-specific fault codes no longer apply.
    first = test.index('        // Sequential load identity')
    last = test.index('        file=$fopen', first)
    test = test[:first]+test[last:]
    wires = '''
    logic history_req_valid,history_req_ready,history_rsp_valid,history_rsp_ready;
    logic [1:0] history_op;
    logic [63:0] history_a,history_b,history_value;
    logic [3:0] history_faults;
'''
    test = test.replace('    main_heart_history_window dut(', wires+'    main_heart_history_window dut(')
    names = ('req_valid','req_ready','rsp_valid','rsp_ready','op','a','b','value','faults')
    connections = ','.join(f'.history_{name}(history_{name})' for name in names)
    anchor = '.math_value(value),.math_faults(mf));'
    if test.count(anchor) != 1: raise ValueError('history test wiring anchor changed')
    test = test.replace(anchor, '.math_value(value),.math_faults(mf),'+connections+');')
    start = test.index("        .history_req_valid(1'b0)")
    end = test.index("        .bank_req_valid", start)
    test = test[:start]+'        '+connections+',\n'+test[end:]
    test = test.replace('MAIN_HEART_ASSESSMENT_PASS', 'MAIN_HEART_HISTORY_ASSESSMENT_PASS')
    test = test.replace('    initial begin #(64\'d10000000000);', '''    // Perturb only the upstream BRAM output between clock edges. A captured
    // transfer must remain stable during the receiver's accepting cycle.
    // Release before any accepting edge, so no golden value is substituted.
    logic [63:0] transfer_saved;
    initial begin
        wait(reset_n && dut.aload && !dut.hload);
        @(negedge clk);
        transfer_saved=dut.assessor.load_value;
        force dut.hvalue=64'h3ff123456789abcd;
        #1;
        if(dut.assessor.load_value!==transfer_saved)
            $fatal(1,"history BRAM output reaches assessment without a register");
        release dut.hvalue;
        $display("MAIN_HEART_HISTORY_REGISTERED_TRANSFER_PASS");
    end
    initial begin #(64'd10000000000);''')
    tb = output/'tb_main_heart_history_assessment.sv'
    with tb.open('x', encoding='utf-8') as stream: stream.write(test)
    sources = (fp, *derived, ROOT/'rtl/history100_mul53.sv', ROOT/'rtl/main_heart_mul53.sv',
        ROOT/'rtl/main_heart_fp64_arbiter.sv', hub, history, ROOT/'rtl/main_heart_assessment.sv',
        stage_window(output), tb)
    compiled = compile_xsim(sources, 'tb_main_heart_history_assessment', output)
    ran = run_tool('xsim', ['tb_main_heart_history_assessment', '--R', '--log', str(output/'native.log')], output, timeout=1800)
    found = re.findall(r'MAIN_HEART_HISTORY_ASSESSMENT_PASS windows=(\d+) words=(\d+) max_cycles=(\d+) reset=1 cancel=1 stalls=1 malformed=1', ran['stdout'])
    if len(found) != 1 or list(map(int, found[0][:2])) != [287,6027] or source_hashes(sources) != compiled['source_hashes']:
        raise ValueError('full history assessment proof incomplete or source changed')
    if ran['stdout'].count('MAIN_HEART_HISTORY_REGISTERED_TRANSFER_PASS') != 1:
        raise ValueError('registered history transfer not exercised')
    result = dict(passed=True, windows=287, assessment_words_checked=6027, word_differences=0,
        decision_differences=0, primitives_supplied_by_hardware=True, registered_transfer_checked=True, max_cycles=int(found[0][2]),
        compile=compiled, simulation_log=ran['log'], original_sources=frozen, hardware_accessed=False,
        full_main_chain_verified=False, full_transaction_budget_passed=False)
    with (output/'result.json').open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2)
    return result
