"""Fixed100-point original pocketfft real butterflies and Welch order.

Derived from SciPy1.8.0 pocketfft_hdronly.h (3-clause BSD); preserve operation
order, factorization4/5/5 and binary64. Host sin/cos constants are candidates
until the saved ARM FFT gate passes; they are never substituted as goldens.
"""
from functools import lru_cache
import hashlib
import math
from pathlib import Path
import struct
import heapq
import json
import re

from .main_heart_operators import arm_cases, word, number

ROOT = Path(__file__).resolve().parent
SOURCE = Path('E:/Codex-builds/v3b25-main-heart-fft-source-20261026-01/pocketfft_hdronly.h')
SOURCE_SHA = '9ceede8f82b66a1db731903e8fa99d632da6b6347492279881511672f15ba0b6'


def decode(encoded):
    raw = bytes.fromhex(encoded[2])
    return list(struct.unpack('<'+'d'*(len(raw)//8), raw))


def binary(values): return struct.pack('<'+'d'*len(values), *values)


@lru_cache(maxsize=1)
def twiddles():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA:
        raise ValueError('original pocketfft source changed')
    ang = (.25*float('3.141592653589793238462643383279502884197'))/100
    def calc(index):
        x, n = index*8, 100
        if x < 400:
            if x < 200:
                if x < n: return math.cos(x*ang), math.sin(x*ang)
                return math.sin((2*n-x)*ang), math.cos((2*n-x)*ang)
            x -= 200
            if x < n: return -math.sin(x*ang), math.cos(x*ang)
            return -math.cos((2*n-x)*ang), math.sin((2*n-x)*ang)
        x = 800-x
        if x < 200:
            if x < n: return math.cos(x*ang), -math.sin(x*ang)
            return math.sin((2*n-x)*ang), -math.cos((2*n-x)*ang)
        x -= 200
        if x < n: return -math.sin(x*ang), -math.cos(x*ang)
        return -math.cos((2*n-x)*ang), -math.sin((2*n-x)*ang)
    v1 = [(1.,0.)]+[calc(i) for i in range(1,8)]
    v2 = [(1.,0.)]+[calc(i*8) for i in range(1,7)]
    values = []
    for index in range(51):
        a,b = v1[index&7], v2[index>>3]
        values.append((a[0]*b[0]-a[1]*b[1], a[0]*b[1]+a[1]*b[0]))
    return tuple(values)


def _radf(ido, l1, cc, ip, wa):
    out = [None]*100
    def c(a,b,d): return cc[a+ido*(b+l1*d)]
    def put(a,b,k,v): out[a+ido*(b+ip*k)] = v
    def pm(a,b): return a+b, a-b
    def mulpm(j,i,k):
        a,b = wa[(j-1)*(ido-1)+i-2: (j-1)*(ido-1)+i]
        e,f = c(i-1,k,j),c(i,k,j)
        return a*e+b*f, a*f-b*e
    if ip == 4:
        for k in range(l1):
            tr1, v = pm(c(0,k,3), c(0,k,1)); put(0,2,k,v)
            tr2, v = pm(c(0,k,0), c(0,k,2)); put(ido-1,1,k,v)
            a,b = pm(tr2,tr1); put(0,0,k,a); put(ido-1,3,k,b)
        # The fixed100 factorization has ido25, never an even ido.
        if ido % 2 == 0: raise ValueError('unexpected fixed100 even radix4 ido')
        for k in range(l1):
            for i in range(2,ido,2):
                ic = ido-i
                cr2,ci2 = mulpm(1,i,k);cr3,ci3 = mulpm(2,i,k);cr4,ci4 = mulpm(3,i,k)
                tr1,tr4 = pm(cr4,cr2);ti1,ti4 = pm(ci2,ci4)
                tr2,tr3 = pm(c(i-1,k,0),cr3);ti2,ti3 = pm(c(i,k,0),ci3)
                a,b = pm(tr2,tr1);put(i-1,0,k,a);put(ic-1,3,k,b)
                a,b = pm(ti1,ti2);put(i,0,k,a);put(ic,3,k,b)
                a,b = pm(tr3,ti4);put(i-1,2,k,a);put(ic-1,1,k,b)
                a,b = pm(tr4,ti3);put(i,2,k,a);put(ic,1,k,b)
    elif ip == 5:
        tr11,ti11,tr12,ti12 = [float(x) for x in ('0.3090169943749474241022934171828191',
            '0.9510565162951535721164393333793821','-0.8090169943749474241022934171828191',
            '0.5877852522924731291687059546390728')]
        for k in range(l1):
            cr2,ci5 = pm(c(0,k,4),c(0,k,1)); cr3,ci4 = pm(c(0,k,3),c(0,k,2))
            put(0,0,k,(c(0,k,0)+cr2)+cr3)
            put(ido-1,1,k,(c(0,k,0)+tr11*cr2)+tr12*cr3)
            put(0,2,k,ti11*ci5+ti12*ci4)
            put(ido-1,3,k,(c(0,k,0)+tr12*cr2)+tr11*cr3)
            put(0,4,k,ti12*ci5-ti11*ci4)
        for k in range(l1):
            for i in range(2,ido,2):
                ic=ido-i
                dr2,di2=mulpm(1,i,k);dr3,di3=mulpm(2,i,k)
                dr4,di4=mulpm(3,i,k);dr5,di5=mulpm(4,i,k)
                dr2,di2,dr5,di5 = dr2+dr5, di2+di5, di2-di5, dr5-dr2
                dr3,di3,dr4,di4 = dr3+dr4, di3+di4, di3-di4, dr4-dr3
                put(i-1,0,k,(c(i-1,k,0)+dr2)+dr3)
                put(i,0,k,(c(i,k,0)+di2)+di3)
                tr2=(c(i-1,k,0)+tr11*dr2)+tr12*dr3
                ti2=(c(i,k,0)+tr11*di2)+tr12*di3
                tr3=(c(i-1,k,0)+tr12*dr2)+tr11*dr3
                ti3=(c(i,k,0)+tr12*di2)+tr11*di3
                tr5=ti11*dr5+ti12*dr4;ti5=ti11*di5+ti12*di4
                tr4=ti12*dr5-ti11*dr4;ti4=ti12*di5-ti11*di4
                a,b=pm(tr2,tr5);put(i-1,2,k,a);put(ic-1,1,k,b)
                a,b=pm(ti5,ti2);put(i,2,k,a);put(ic,1,k,b)
                a,b=pm(tr3,tr4);put(i-1,4,k,a);put(ic-1,3,k,b)
                a,b=pm(ti4,ti3);put(i,4,k,a);put(ic,3,k,b)
    else: raise ValueError('unexpected fixed100 radix')
    if any(v is None for v in out): raise ValueError('radix left unwritten output')
    return out


def fft100(values):
    if len(values) != 100: raise ValueError('FFT requires100 samples')
    tw = twiddles()
    factors = []
    l1=1
    for ip in (4,5,5):
        ido=100//(l1*ip)
        wa=[0.]*((ip-1)*(ido-1))
        if ido>1:
            for j in range(1,ip):
                for i in range(1,(ido-1)//2+1):
                    re,im = tw[j*l1*i]
                    wa[(j-1)*(ido-1)+2*i-2] = re
                    wa[(j-1)*(ido-1)+2*i-1] = im
        factors.append((ido,l1,ip,wa))
        l1 *= ip
    data = list(values)
    for ido,l1,ip,wa in reversed(factors): data = _radf(ido,l1,data,ip,wa)
    return [data[0],0.] + [v for i in range(1,50) for v in (data[2*i-1],data[2*i])] + [data[99],0.]


def qualify_fft():
    count=0
    for ci, row in enumerate(arm_cases()):
        for wi, item in enumerate(row['welch']):
            actual=binary(fft100(decode(item['fft_input'])))
            expected=bytes.fromhex(item['fft_output'][2])
            if actual != expected:
                bad=[i for i in range(102) if actual[i*8:i*8+8] != expected[i*8:i*8+8]]
                raise ValueError(f'original FFT order differs case{ci} window{wi}, words{bad[:10]}')
            count+=1
    return dict(observations=count,complex_words_checked=count*102,differences=0,
                factorization=[4,5,5],rtl_verified=False,source_sha256=SOURCE_SHA)


def original_sum(values):
    """Original NumPy pairwise reduction for the bounded lengths used here."""
    if len(values) < 8:
        result = -0.
        for value in values: result = result+value
    else:
        lanes = list(values[:8])
        stop = len(values)//8*8
        for i in range(8,stop): lanes[i%8] = lanes[i%8]+values[i]
        result = ((lanes[0]+lanes[1])+(lanes[2]+lanes[3])) + ((lanes[4]+lanes[5])+(lanes[6]+lanes[7]))
        for value in values[stop:]: result = result+value
    return 0.+result


@lru_cache(maxsize=1)
def hann():
    result = tuple(decode(arm_cases()[0]['welch'][0]['window']))
    if hashlib.sha256(binary(result)).hexdigest() != '41393f80ea4e2c96e0cd99dfaa2f6f52300e296e6fa3932ba8ed6a24dd0ce050':
        raise ValueError('original ARM Hann differs')
    return result


def welch100(values):
    if len(values) != 100: raise ValueError('Welch requires100 samples')
    mean = original_sum(values)/100.
    centered = [v-mean for v in values]
    windowed = [v*w for v,w in zip(centered,hann())]
    transformed = fft100(windowed)
    scale = 1./(25.*original_sum([v*v for v in hann()]))
    density = []
    for i in range(51):
        re,im=transformed[2*i:2*i+2]
        psd = (re*re+im*im)*scale
        if 0 < i < 50: psd = psd*2.
        density.append(psd)
    integral = original_sum([(.25*(density[i]+density[i+1]))/2. for i in range(3,12)])
    return integral, dict(mean=mean, centered=centered, windowed=windowed, transformed=transformed, density=density, scale=scale)


def qualify_welch():
    count = 0
    for ci,row in enumerate(arm_cases()):
        for wi,item in enumerate(row['welch']):
            power, stages = welch100(decode(item['input']))
            for actual,name in ((stages['centered'],'detrended'),(stages['windowed'],'fft_input'),
                                (stages['transformed'],'fft_output'),(stages['density'],'psd')):
                got=binary(actual); want=bytes.fromhex(item[name][2])
                if got != want:
                    bad=[i for i in range(len(actual)) if got[i*8:i*8+8] != want[i*8:i*8+8]]
                    raise ValueError(f'ARM Welch {name} differs case{ci} window{wi}: {bad[:8]}')
            if word(power) != int(item['band_power'],16) or word(stages['scale']) != int(item['scale'],16):
                raise ValueError(f'ARM Welch power/scale differs case{ci} window{wi}')
            count+=1
    return dict(observations=count,band_powers_checked=count,differences=0,rtl_verified=False)


class Value:
    def __init__(self, engine, index): self.engine,self.index=engine,index
    def __add__(self, other): return self.engine.emit(0,self,other)
    def __radd__(self, other): return self.engine.emit(0,other,self)
    def __sub__(self, other): return self.engine.emit(1,self,other)
    def __rsub__(self, other): return self.engine.emit(1,other,self)
    def __mul__(self, other): return self.engine.emit(2,self,other)
    def __rmul__(self, other): return self.engine.emit(2,other,self)
    def __truediv__(self, other): return self.engine.emit(3,self,other)


class Expressions:
    def __init__(self):
        self.count=100;self.instructions=[];self.constants={}
    def operand(self, value):
        if isinstance(value,Value):
            if value.engine is not self: raise ValueError('mixed expression graphs')
            return value.index
        bits=word(value)
        if bits not in self.constants:
            self.constants[bits]=self.count;self.count+=1
        return self.constants[bits]
    def emit(self, op, a, b):
        a,b=self.operand(a),self.operand(b)
        result=self.count;self.count+=1
        self.instructions.append((op,result,a,b))
        return Value(self,result)


def welch_program():
    """Only original operations, with liveness-based RAM slot reuse."""
    e=Expressions()
    output,_=welch100([Value(e,i) for i in range(100)])
    uses={i:0 for i in range(e.count)}
    for _,_,a,b in e.instructions: uses[a]+=1;uses[b]+=1
    uses[output.index]+=1
    initial=list(range(100))+list(e.constants.values())
    addresses={i:n for n,i in enumerate(initial)}
    next_address=len(initial);free=[];program=[]
    for op,dst,a,b in e.instructions:
        left,right=addresses[a],addresses[b]
        for old in (a,b):
            uses[old]-=1
            if uses[old]==0: heapq.heappush(free,addresses[old])
        if free: address=heapq.heappop(free)
        else: address=next_address;next_address+=1
        addresses[dst]=address
        program.append((op,address,left,right))
    if next_address>512: raise ValueError('Welch graph exceeds bounded data RAM')
    return dict(program=program, output_address=addresses[output.index],
                constants=list(e.constants), slots=next_address, inputs=100)


def write_welch_assets(output):
    output=Path(output)
    graph=welch_program()
    with (output/'main_welch_constants.mem').open('x',encoding='ascii') as stream:
        for value in graph['constants']: stream.write(f'{value:016x}\n')
    with (output/'main_welch_program.mem').open('x',encoding='ascii') as stream:
        for op,dst,a,b in graph['program']:
            stream.write(f'{(op<<28)|(dst<<18)|(a<<9)|b:08x}\n')
        stream.write(f'{(4<<28)|(graph["output_address"]<<9):08x}\n')
    observations=[item for row in arm_cases() for item in row['welch']]
    with (output/'main_welch_vectors.txt').open('x',encoding='ascii') as stream:
        stream.write(str(len(observations))+'\n')
        for item in observations:
            stream.write(item['band_power']+'\n')
            for value in decode(item['input']): stream.write(f'{word(value):016x}\n')
    return graph,len(observations)


def run_welch_rtl(output):
    from .history100_dsp import stage
    from v2_offline_arena.heart_v3a.rtl_sim import compile_xsim,run_tool,source_hashes
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    graph,count=write_welch_assets(output)
    fp=stage(output/'history100_fp64.sv')
    sources=(fp,ROOT/'rtl/history100_mul53.sv',ROOT/'rtl/main_heart_welch.sv',ROOT/'sim/tb_main_heart_welch.sv')
    compiled=compile_xsim(sources,'tb_main_heart_welch',output)
    ran=run_tool('xsim',['tb_main_heart_welch','--R','--log',str(output/'native.log')],output,timeout=600)
    found=re.findall(r'MAIN_HEART_WELCH_PASS checked=(\d+) max_cycles=(\d+) reset=1 cancel=1 stalls=1 invalid=1',ran['stdout'])
    if len(found)!=1 or int(found[0][0])!=count or source_hashes(sources)!=compiled['source_hashes']:
        raise ValueError('Welch RTL verification incomplete')
    result=dict(passed=True,windows_checked=count,differences=0,max_cycles=int(found[0][1]),
                reset_checked=True,cancel_checked=True,backpressure_checked=True,invalid_checked=True,
                hardware_accessed=False,compile=compiled,simulation_log=ran['log'],
                operations=len(graph['program']),data_ram_slots=graph['slots'],constant_words=len(graph['constants']),
                source_sha256=SOURCE_SHA)
    with (output/'result.json').open('x',encoding='utf-8') as stream: json.dump(result,stream,indent=2)
    return result
