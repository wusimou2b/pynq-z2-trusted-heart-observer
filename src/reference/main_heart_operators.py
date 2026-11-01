"""Original ARM libm operation order and supplemental ARM operator fixtures.

Log operations follow the recorded Cortex-A9 Thumb/VFP implementation, with
separately rounded VMLA multiply/add. Constants are read from the pinned ELF.
Algorithm provenance: glibc dbl-64 e_log/e_log10 (LGPL-2.1-or-later; Sun notice
on e_log10). The original library and all successful hardware stay untouched.
"""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import struct
from zipfile import ZipFile
import re

ROOT = Path(__file__).resolve().parent
LIBM = ROOT.parent/'v2_offline_arena/v3a50_algorithm_research/pl_arm_implementation/evidence/board-arm-implementation-044e723fea67/libraries/02-libm.so.6'
LIBM_SHA = '7f74c8ad98821e110bd5aac33ea10efed61f1e40687403f16014904164719d0b'
REFERENCE = Path('E:/Codex-builds/v3b25-main-heart-arm-review-20261026-02/main-heart-arm-reference-results.zip')
REFERENCE_SHA = '2ad01d6fe7b503247aa958e34c5b3779ad2ecbb49382e5aaec6ac4a86ac71740'
MASK = (1 << 64)-1


def word(value): return struct.unpack('>Q', struct.pack('>d', value))[0]
def number(value): return struct.unpack('>d', struct.pack('>Q', value))[0]


@lru_cache(maxsize=1)
def math_constants():
    raw = LIBM.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LIBM_SHA: raise ValueError('original ARM libm differs')
    header = struct.unpack_from('<HHIIIIIHHHHHH', raw, 16)
    segments = [struct.unpack_from('<IIIIIIII', raw, header[4]+i*header[8]) for i in range(header[9])]
    def read(address, size):
        found = [s[1]+address-s[2] for s in segments if s[0] == 1 and s[2] <= address and address+size <= s[2]+s[4]]
        if len(found) != 1: raise ValueError('ambiguous libm data address')
        return raw[found[0]:found[0]+size]
    # Literal pool 10c68 + Thumb PC10ab4 identifies this original table.
    base = struct.unpack('<I', read(0x10c68, 4))[0] + 0x10ab4
    if base != 0x3b670: raise ValueError('libm log table changed')
    constants = list(struct.unpack('<18Q', read(base, 18*8)))
    for i in range(128):
        constants.extend(struct.unpack('<2Q', read(base+0x90+16*i, 16)))
        constants.extend(struct.unpack('<2Q', read(base+0x890+16*i, 16)))
    constants.extend(struct.unpack('<3Q', read(0x10d38, 24)))
    if constants[-3:] != [0x3fdbcb7b1526e50e, 0x3d59fef311f12b36, 0x3fd34413509f6000]:
        raise ValueError('log10 constants differ')
    return tuple(constants)


@lru_cache(maxsize=1)
def arm_cases():
    raw = REFERENCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REFERENCE_SHA: raise ValueError('operator reference identity differs')
    with ZipFile(REFERENCE) as z:
        if z.testzip() is not None: raise ValueError('operator reference CRC differs')
        rows = [json.loads(line) for start in range(0, 287, 48)
                for line in z.read(f'cases-{start:03d}.jsonl').splitlines()]
    if len(rows) != 287: raise ValueError('operator reference coverage differs')
    return tuple(rows)


class Program:
    """SSA instructions for individually rounded add/subtract/multiply."""
    def __init__(self): self.instructions = []
    def op(self, operation, a, b):
        destination = 32+len(self.instructions)
        self.instructions.append((operation, destination, a, b))
        return destination
    def add(self, a, b): return self.op(0, a, b)
    def sub(self, a, b): return self.op(1, a, b)
    def mul(self, a, b): return self.op(2, a, b)
    def mla(self, accumulator, a, b): return self.add(accumulator, self.mul(a, b))


@lru_cache(maxsize=2)
def log_program(near):
    p = Program()
    # Seed0 normalized input;1 log10 exponent;2/3 Ln2;4..8 A;
    # 9..19 B;20 invc;21 logc;22 chi;23 clo;24 log exponent;
    # 25 2^27;26 one;27..29 log10 constants;30 reduced z.
    if not near:
        r = p.mul(p.sub(p.sub(30, 22), 23), 20)
        w = p.mla(21, 24, 2)
        u = p.mla(5, r, 6)
        hi = p.add(r, w)
        t = p.mla(7, r, 8)
        lo = p.add(p.sub(w, hi), r)
        lo = p.mla(lo, 24, 3)
        r2 = p.mul(r, r)
        u = p.mla(u, t, r2)
        lo = p.mla(lo, r2, 4)
        r3 = p.mul(r, r2)
        y = p.mla(lo, u, r3)
        y = p.add(y, hi)
    else:
        # Exact VFP data flow at10b4a..10bea. Recreate without high-level
        # reassociation; early temporary order itself does not affect results.
        p = Program()
        r = p.sub(0, 26)
        r2 = p.mul(r, r)
        a = p.mla(16, r, 17)
        w = p.mul(r, 25)
        r3 = p.mul(r, r2)
        a = p.mla(a, r2, 18)
        rhi = p.add(r, w)
        b = p.mla(13, r, 14)
        a = p.mla(a, r3, 19)
        rhi = p.sub(rhi, w)
        b = p.mla(b, r2, 15)
        c = p.mla(10, r, 11)
        b = p.mla(b, a, r3)
        square = p.mul(rhi, rhi)
        c = p.mla(c, r2, 12)
        rlo = p.sub(r, rhi)
        rsum = p.add(r, rhi)
        square = p.mul(square, 9)
        rlo = p.mul(rlo, 9)
        hi = p.add(r, square)
        c = p.mla(c, b, r3)
        lo = p.add(p.sub(r, hi), square)
        lo = p.mla(lo, rlo, rsum)
        lo = p.mla(lo, c, r3)
        y = p.add(hi, lo)
    result = p.mul(y, 27)
    result = p.mla(result, 1, 28)
    result = p.mla(result, 1, 29)
    return tuple(p.instructions), result


def log_seeds(value):
    if type(value) is not int or not 0 < value < 0x7ff0000000000000:
        raise ValueError('log10 requires positive finite binary64')
    fraction, exponent = value & ((1 << 52)-1), value >> 52
    if exponent == 0:
        shift = 53-fraction.bit_length()
        fraction = (fraction << shift) & ((1 << 52)-1)
        k = -1022-shift
    else: k = exponent-1023
    normalized = fraction | ((1022 if k < 0 else 1023) << 52)
    y = k + int(k < 0)
    tmp = (normalized-0x3fe6000000000000) & MASK
    index = (tmp >> 45) & 127
    log_k = (tmp-(1 << 64) if tmp >> 63 else tmp) >> 52
    z = (normalized-(tmp & 0xfff0000000000000)) & MASK
    c = math_constants()
    seeds = [0]*32
    seeds[0], seeds[1] = normalized, word(float(y))
    seeds[2:9] = c[:7]
    seeds[9:20] = c[7:18]
    seeds[20:24] = c[18+index*4:22+index*4]
    seeds[24:27] = [word(float(log_k)), 0x41a0000000000000, 0x3ff0000000000000]
    seeds[27:30] = c[-3:]
    seeds[30] = z
    return seeds, 0x3fee000000000000 <= normalized < 0x3ff1090000000000


def log10_word(value):
    seeds, near = log_seeds(value)
    registers = list(map(number, seeds)) + [0.]*128
    instructions, result = log_program(near)
    for op, dst, a, b in instructions:
        registers[dst] = (registers[a]+registers[b] if op == 0 else
                          registers[a]-registers[b] if op == 1 else registers[a]*registers[b])
    return word(registers[result])


def qualify_log10_profile():
    result = dict(calls=0, differences=0, near_one_calls=0, table_calls=0, host_math_used=False,
                  library_sha256=LIBM_SHA, reference_sha256=REFERENCE_SHA, rtl_verified=False)
    for index, row in enumerate(arm_cases()):
        for call in row['scalar_calls']['log10']:
            arg = int(call['args'][0], 16)
            actual = log10_word(arg)
            if actual != int(call['result'], 16):
                raise ValueError(f'ARM log10 differs case{index}: {arg:016x} -> {actual:016x}, want {call["result"]}')
            result['near_one_calls' if log_seeds(arg)[1] else 'table_calls'] += 1
            result['calls'] += 1
    return result


def write_log_assets(output):
    output = Path(output)
    with (output/'main_log_math.mem').open('x', encoding='ascii') as stream:
        for value in math_constants(): stream.write(f'{value:016x}\n')
    program = [0xff000000]*128
    for near, base in ((False, 0), (True, 64)):
        instructions, result = log_program(near)
        for index, (op, dst, a, b) in enumerate(instructions):
            program[base+index] = (op << 24) | (dst << 16) | (a << 8) | b
        program[base+len(instructions)] = (3 << 24) | (result << 8)
    with (output/'main_log_program.mem').open('x', encoding='ascii') as stream:
        for value in program: stream.write(f'{value:08x}\n')
    vectors = [(int(c['args'][0],16), int(c['result'],16), 0)
               for row in arm_cases() for c in row['scalar_calls']['log10']]
    count = len(vectors)
    vectors += [(word(x), word(y), 0) for x,y in ((1.,0.),(10.,1.),(100.,2.),(1000.,3.))]
    vectors += [(x,0x7ff8000000000000,1) for x in
                (0, 1<<63, 0xbff0000000000000, 0x7ff0000000000000, 0x7ff8000000000000)]
    with (output/'main_log_vectors.txt').open('x', encoding='ascii') as stream:
        stream.write(str(len(vectors))+'\n')
        for a, b, fault in vectors: stream.write(f'{a:016x} {b:016x} {fault:x}\n')
    return count, len(vectors)


def run_log10_rtl(output):
    from .history100_dsp import stage
    from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim, run_tool, source_hashes
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    arm_count, total = write_log_assets(output)
    fp = stage(output/'history100_fp64.sv')
    sources = (fp, ROOT/'rtl/history100_mul53.sv', ROOT/'rtl/main_heart_log10.sv', ROOT/'sim/tb_main_heart_log10.sv')
    compiled = compile_xsim(sources, 'tb_main_heart_log10', output)
    ran = run_tool('xsim', ['tb_main_heart_log10', '--R', '--log', str(output/'native.log')], output, timeout=300)
    found = re.findall(r'MAIN_HEART_LOG10_PASS checked=(\d+) max_cycles=(\d+) reset=1 cancel=1 stalls=1', ran['stdout'])
    if len(found) != 1 or int(found[0][0]) != total or source_hashes(sources) != compiled['source_hashes']:
        raise ValueError('log10 RTL verification incomplete')
    result = dict(passed=True, arm_calls_checked=arm_count, checked=total, differences=0,
                  max_cycles=int(found[0][1]), reset_checked=True, cancel_checked=True, backpressure_checked=True,
                  hardware_accessed=False, compile=compiled, simulation_log=ran['log'],
                  source_library_sha256=LIBM_SHA, reference_sha256=REFERENCE_SHA,
                  asset_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in output.glob('main_log_*') if p.is_file()})
    with (output/'result.json').open('x', encoding='utf-8') as stream: json.dump(result, stream, indent=2)
    return result


@lru_cache(maxsize=1)
def pow_constants():
    raw=LIBM.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=LIBM_SHA: raise ValueError('ARM pow library changed')
    header=struct.unpack_from('<HHIIIIIHHHHHH',raw,16)
    segments=[struct.unpack_from('<IIIIIIII',raw,header[4]+i*header[8]) for i in range(header[9])]
    def read(address,size):
        matches=[s[1]+address-s[2] for s in segments if s[0]==1 and s[2]<=address and address+size<=s[2]+s[4]]
        if len(matches)!=1: raise ValueError('pow data address differs')
        return raw[matches[0]:matches[0]+size]
    logbase=0x10dc6+struct.unpack('<I',read(0x11418,4))[0]
    expbase=0x10ef2+struct.unpack('<I',read(0x1141c,4))[0]
    if (logbase,expbase)!=(0x3cf90,0x3ae00):raise ValueError('pow tables differ')
    header=list(struct.unpack('<9d',read(logbase,72)))
    logtable=[struct.unpack('<4d',read(logbase+72+32*i,32)) for i in range(128)]
    expheader=struct.unpack('<8d',read(expbase,64))
    exptable=struct.unpack('<256Q',read(expbase+112,2048))
    return header,logtable,expheader,exptable


def arm_pow2(value):
    """Original __pow(x,2) non-fused operation order, including exp scaling."""
    ix=word(value)
    if value==0.:return 0.
    if ix>>63 or ix>=0x7ff0000000000000:raise ValueError('finite nonnegative pow2 required')
    h,table,eh,et=pow_constants()
    if ix>>52==0:ix=(word(value*float.fromhex('0x1p52'))-(52<<52))&MASK
    tmp=(ix-0x3fe6955500000000)&MASK
    i=(tmp>>45)&127
    k=(tmp-(1<<64) if tmp>>63 else tmp)>>52
    iz=(ix-(tmp&0xfff0000000000000))&MASK
    z=number(iz);zhi=number((iz+(1<<31))&0xffffffff00000000);zlo=z-zhi
    invc,_,logc,logctail=table[i]
    rhi=zhi*invc-1.;rlo=zlo*invc;r=rhi+rlo
    t1=logc+float(k)*h[0];t2=r+t1
    lo1=logctail+float(k)*h[1];lo2=(t1-t2)+r
    a=h[2:];ar=a[0]*r;ar2=r*ar;ar3=r*ar2
    arhi=a[0]*rhi;arhi2=rhi*arhi;hi=t2+arhi2
    lo3=rlo*(ar+arhi);lo4=(t2-hi)+arhi2
    p=ar3*((a[1]+r*a[2])+ar2*((a[3]+r*a[4])+ar2*(a[5]+r*a[6])))
    lo=(((lo1+lo2)+lo3)+lo4)+p
    hi_total=hi+lo;tail=(hi-hi_total)+lo
    lhi=number(word(hi_total)&0xfffffffff8000000)
    llo=(hi_total-lhi)+tail
    ehi=2.*lhi;elo=0.*lhi+2.*llo
    if abs(ehi)<float.fromhex('0x1p-54'):return 1.+ehi
    if abs(ehi)>=1024.:return 0. if ehi<0 else float('inf')
    invln2,shift,neg_hi,neg_lo,c2,c3,c4,c5=eh
    kd0=shift+ehi*invln2;ki=word(kd0);kd=kd0-shift
    r=(ehi+kd*neg_hi)+kd*neg_lo;r=elo+r
    idx=2*(ki%128)
    scale_word=(et[idx+1]+((ki<<45)&MASK))&MASK
    r2=r*r
    poly=((r+number(et[idx]))+(c2+r*c3)*r2)+(c4+r*c5)*(r2*r2)
    if abs(ehi)>=512.:
        if not ki&(1<<31):
            scale=number((scale_word-(1009<<52))&MASK)
            return float.fromhex('0x1p1009')*(scale+scale*poly)
        scale=number((scale_word+(1022<<52))&MASK)
        y=scale+scale*poly
        if abs(y)<1.:
            one=-1. if y<0 else 1.
            lo=(scale-y)+scale*poly;hi=one+y
            lo=((one-hi)+y)+lo;y=(hi+lo)-one
            if y==0.:y=0.
        return float.fromhex('0x1p-1022')*y
    scale=number(scale_word)
    return scale+scale*poly


def qualify_gain_arguments():
    from .main_heart_reference import load_cases
    checked=plain=0
    for ci,(source,row) in enumerate(zip(load_cases(),arm_cases())):
        maxima=struct.unpack('<12d',bytes.fromhex(source['maxima']))
        inputs=[];multiplications=[]
        for j in range(4):
            if source['active_reference_mask'][j]:
                for signal in (1,2):
                    x,y=maxima[j],maxima[4*signal+j]
                    inputs.append((arm_pow2(x)+1e-12)/(arm_pow2(y)+1e-12))
                    multiplications.append((x*x+1e-12)/(y*y+1e-12))
        for arg,mul,call in zip(inputs,multiplications,row['scalar_calls']['log10']):
            if word(arg)!=int(call['args'][0],16):
                raise ValueError(f'original ARM pow2 gain argument differs case{ci}: {word(arg):016x}/{call["args"][0]}')
            checked+=1;plain+=word(mul)!=int(call['args'][0],16)
    return dict(calls=checked,differences=0,plain_multiply_differences=plain,rtl_verified=False)


def pow_program():
    p=Program()
    # Seeds2..10 log header;11/12/13 invc/logc/logctail;14/15 z/zhi;
    # 16 kd;17 one;18 two;19 zero;20..27 exp header;28/29 tail/scale.
    zlo=p.sub(14,15);rhi=p.sub(p.mul(15,11),17);rlo=p.mul(zlo,11);r=p.add(rhi,rlo)
    t1=p.mla(12,16,2);t2=p.add(r,t1)
    lo1=p.mla(13,16,3);lo2=p.add(p.sub(t1,t2),r)
    ar=p.mul(4,r);ar2=p.mul(r,ar);ar3=p.mul(r,ar2)
    arhi=p.mul(4,rhi);arhi2=p.mul(rhi,arhi);hi=p.add(t2,arhi2)
    lo3=p.mul(rlo,p.add(ar,arhi));lo4=p.add(p.sub(t2,hi),arhi2)
    poly=p.mul(ar3,p.add(p.add(5,p.mul(r,6)),p.mul(ar2,p.add(p.add(7,p.mul(r,8)),p.mul(ar2,p.add(9,p.mul(r,10)))))))
    lo=p.add(p.add(p.add(p.add(lo1,lo2),lo3),lo4),poly)
    total=p.add(hi,lo);tail=p.add(p.sub(hi,total),lo)
    lhi=p.op(4,total,0)
    llo=p.add(p.sub(total,lhi),tail)
    ehi=p.mul(18,lhi);elo=p.add(p.mul(19,lhi),p.mul(18,llo))
    p.op(6,ehi,elo)  # Tiny/large exponent branch before exp arithmetic.
    kd0=p.add(21,p.mul(ehi,20));p.op(5,kd0,0)
    kd=p.sub(kd0,21)
    reduced=p.add(elo,p.add(p.add(ehi,p.mul(kd,22)),p.mul(kd,23)))
    r2=p.mul(reduced,reduced)
    poly=p.add(p.add(p.add(reduced,28),p.mul(p.add(24,p.mul(reduced,25)),r2)),
               p.mul(p.add(26,p.mul(reduced,27)),p.mul(r2,r2)))
    result=p.mla(29,29,poly)
    program=list(p.instructions)+[(7,result,29,poly)]
    if len(program)>=128:raise ValueError('pow normal program exceeds partition')
    under=Program()
    low=under.add(under.sub(29,30),under.mul(29,31))
    high=under.add(17,30)
    low=under.add(under.add(under.sub(17,high),30),low)
    y=under.sub(under.add(high,low),17)
    return program,list(under.instructions)+[(8,0,y,0)]


def write_gain_assets(output):
    from .main_heart_reference import load_cases
    output=Path(output)
    h,table,eh,et=pow_constants()
    constants=[word(v) for v in h]+[word(v) for row in table for v in row]+[word(v) for v in eh]+list(et)
    with (output/'main_pow_math.mem').open('x',encoding='ascii') as stream:
        for value in constants:stream.write(f'{value:016x}\n')
    program=[0xff000000]*256
    main,under=pow_program()
    for base,part in ((0,main),(128,under),(192,[(9,0,30,0)]),(224,[(8,0,30,0)])):
        for i,(op,dst,a,b) in enumerate(part):program[base+i]=(op<<24)|(dst<<16)|(a<<8)|b
    with (output/'main_pow_program.mem').open('x',encoding='ascii') as stream:
        for value in program:stream.write(f'{value:08x}\n')
    vectors=[]
    for source,row in zip(load_cases(),arm_cases()):
        m=struct.unpack('<12d',bytes.fromhex(source['maxima']))
        pairs=[(m[j],m[4*k+j]) for j in range(4) if source['active_reference_mask'][j] for k in (1,2)]
        vectors.extend((word(x),word(y),int(c['args'][0],16)) for (x,y),c in zip(pairs,row['scalar_calls']['log10']))
    with (output/'main_gain_vectors.txt').open('x',encoding='ascii') as stream:
        stream.write(str(len(vectors))+'\n')
        for x,y,want in vectors:stream.write(f'{x:016x} {y:016x} {want:016x}\n')
    return len(vectors)


def run_gain_rtl(output):
    from .history100_dsp import stage
    from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim,run_tool,source_hashes
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    count=write_gain_assets(output);fp=stage(output/'history100_fp64.sv')
    sources=(fp,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_pow2.sv',
             ROOT/'rtl/main_heart_gain_argument.sv',ROOT/'sim/tb_main_heart_gain.sv')
    compiled=compile_xsim(sources,'tb_main_heart_gain',output)
    ran=run_tool('xsim',['tb_main_heart_gain','--R','--log',str(output/'native.log')],output,timeout=300)
    found=re.findall(r'MAIN_HEART_GAIN_PASS checked=(\d+) max_cycles=(\d+) reset=1 cancel=1 stalls=1',ran['stdout'])
    if len(found)!=1 or int(found[0][0])!=count or source_hashes(sources)!=compiled['source_hashes']:
        raise ValueError('gain argument RTL proof incomplete')
    result=dict(passed=True,checked=count,differences=0,max_cycles=int(found[0][1]),reset_checked=True,
                cancel_checked=True,backpressure_checked=True,hardware_accessed=False,
                compile=compiled,simulation_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_pow2_rtl(output):
    from .history100_dsp import stage
    from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim,run_tool,source_hashes
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    write_gain_assets(output);fp=stage(output/'history100_fp64.sv')
    def power2(exponent):
        if exponent>=-1022:return (exponent+1023)<<52
        return 1<<(exponent+1074)
    cases=[(0,0,0),(1<<63,0,0),(word(1.),word(1.),0),
           (word(2.),word(4.),0),(word(.5),word(.25),0)]
    cases.extend((power2(k),power2(2*k),0) for k in (-500,-520,-537,500,511))
    cases.extend((power2(k),0,0) for k in (-538,-1022))
    cases.extend((power2(k),0x7ff0000000000000,8) for k in (512,1023))
    cases.append((word(-1.),0x7ff8000000000000,1))
    with (output/'main_pow_vectors.txt').open('x',encoding='ascii') as stream:
        stream.write(str(len(cases))+'\n')
        for a,b,f in cases:stream.write(f'{a:016x} {b:016x} {f:x}\n')
    sources=(fp,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_pow2.sv',ROOT/'sim/tb_main_heart_pow2.sv')
    compiled=compile_xsim(sources,'tb_main_heart_pow2',output)
    ran=run_tool('xsim',['tb_main_heart_pow2','--R','--log',str(output/'native.log')],output,timeout=300)
    found=re.findall(r'MAIN_HEART_POW2_PASS checked=(\d+) max_cycles=(\d+)',ran['stdout'])
    if len(found)!=1 or int(found[0][0])!=len(cases) or source_hashes(sources)!=compiled['source_hashes']:
        raise ValueError('pow2 literal proof incomplete')
    result=dict(passed=True,literal_vectors=len(cases),differences=0,max_cycles=int(found[0][1]),
        underflow_checked=True,overflow_checked=True,signed_zero_checked=True,hardware_accessed=False,
        compile=compiled,simulation_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result


def run_sqrt_rtl(output, *, staged=False):
    from .main_heart_reference import load_cases
    from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim,run_tool,source_hashes
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    vectors=[]
    for row in load_cases():
        squares=struct.unpack('<77Q',bytes.fromhex(row['squares']))
        norms=struct.unpack('<77Q',bytes.fromhex(row['norms']))
        vectors.extend((a,b,0) for a,b in zip(squares,norms))
    vectors.extend((int(c['args'][0],16),int(c['result'],16),0)
                   for row in arm_cases() for c in row['scalar_calls']['sqrt'])
    arm_count=len(vectors)
    vectors.extend((a,b,0) for a,b in ((0,0),(1<<63,1<<63),(word(4.),word(2.)),
                                    (word(0.25),word(0.5))))
    vectors.extend((a,0x7ff8000000000000,1) for a in (word(-1.),0x7ff0000000000000,0x7ff8000000000000))
    with (output/'main_sqrt_vectors.txt').open('x',encoding='ascii') as stream:
        stream.write(str(len(vectors))+'\n')
        for a,b,f in vectors:stream.write(f'{a:016x} {b:016x} {f:x}\n')
    sources=(ROOT/'rtl/main_heart_sqrt.sv',ROOT/'sim/tb_main_heart_sqrt.sv')
    if staged:
        from .main_heart_shared import stage_sources
        derived,_=stage_sources(output)
        sqrt=next(p for p in derived if p.name=='main_shared_sqrt.sv')
        test=(ROOT/'sim/tb_main_heart_sqrt.sv').read_text('utf-8').replace('main_heart_sqrt dut','main_shared_sqrt dut')
        test=test.replace('        f=$fopen("main_sqrt_vectors.txt","r");', '''        for(integer reset_mode=0;reset_mode<2;reset_mode=reset_mode+1)
            for(integer phase=0;phase<3;phase=phase+1) begin
                argument=64'h3ff23456789abcde;req_valid=1;@(negedge clk);req_valid=0;
                while(!((phase==0 && dut.state==dut.ROUND_COMPARE) ||
                        (phase==1 && dut.state==dut.ROUND_INCREMENT) ||
                        (phase==2 && dut.state==dut.ROUND))) @(negedge clk);
                if(reset_mode==0) reset_n=0;else cancel=1;
                @(negedge clk);reset_n=1;cancel=0;repeat(4) @(negedge clk);
                if(rsp_valid || !req_ready) $fatal(1,"sqrt rounding reset/cancel retained response");
            end
        f=$fopen("main_sqrt_vectors.txt","r");''')
        test=test.replace('    integer f,rc,n,cycles,maximum=0,checked=0;', '''    logic [53:0] rounded_saved;
    logic [52:0] root_saved;
    initial begin
        wait(reset_n && dut.state==dut.ROUND);@(negedge clk);
        rounded_saved=dut.rounded;root_saved=dut.root;
        force dut.root=53'd0;
        #1;if(dut.rounded!==rounded_saved) $fatal(1,"sqrt pack still contains compare/increment chain");
        release dut.root;dut.root=root_saved;
        $display("MAIN_HEART_SQRT_REGISTERED_ROUND_PASS");
    end
    integer f,rc,n,cycles,maximum=0,checked=0;''')
        tb=output/'tb_main_timed_sqrt.sv'
        with tb.open('x',encoding='utf-8') as stream:stream.write(test)
        sources=(sqrt,tb)
    compiled=compile_xsim(sources,'tb_main_heart_sqrt',output)
    ran=run_tool('xsim',['tb_main_heart_sqrt','--R','--log',str(output/'native.log')],output,timeout=300)
    found=re.findall(r'MAIN_HEART_SQRT_PASS checked=(\d+) max_cycles=(\d+) reset=1 cancel=1 stalls=1',ran['stdout'])
    if len(found)!=1 or int(found[0][0])!=len(vectors) or source_hashes(sources)!=compiled['source_hashes']:
        raise ValueError('sqrt RTL proof incomplete')
    if staged and ran['stdout'].count('MAIN_HEART_SQRT_REGISTERED_ROUND_PASS')!=1:
        raise ValueError('sqrt registered pack not exercised')
    result=dict(passed=True,checked=len(vectors),arm_words_checked=arm_count,differences=0,
                max_cycles=int(found[0][1]),reset_checked=True,cancel_checked=True,backpressure_checked=True,
                hardware_accessed=False,compile=compiled,simulation_log=ran['log'])
    with (output/'result.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2)
    return result
