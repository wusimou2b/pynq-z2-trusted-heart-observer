"""Synthetic numerical checks and direct/IPC budgets, never a board acceptance."""
from dataclasses import asdict, replace
import math
import platform
import sys
import time
from heart_v2.runtime_main_chain import Observation
from heart_v3a.runtime_backend import FixedNlmsBackend
from peak_chain import PeakTimingChain
from rate25_tools.reporting import distribution
from .frontend import Frontend25
from .bridge import Bridge25
from .assessment import FLAGS


def average2_response():
    gain=abs(math.cos(math.pi*12.5/50))
    return dict(magnitude_at_12_5hz=gain,attenuation_at_12_5hz_db=-20*math.log10(gain),
        satisfies_old_40db_stopband=False,
        scope_cn='理想两点均值响应，不是实测MAX30102滤波/舍入/时钟；降采后的软件滤波不能消除已混叠分量。')


def inputs(bpm,count):
    # Ideal two-sample average approximates the hardware amplitude response.
    # It does not model device integer rounding, noise, latency or clock phase.
    for i in range(count):
        ir=sum(125000+600*math.sin(2*math.pi*(bpm/60)*(2*i+j)/50) for j in (0,1))/2
        yield Observation(i,i/25.,ir,(0.,0.,1.),True)


def synthetic_case(bpm,count=800):
    front,chain=Frontend25(),PeakTimingChain(FixedNlmsBackend())
    allowed=[]; forbidden=0
    for i,ob in enumerate(inputs(bpm,count)):
        frame=chain.step(front.push(ob)).frame
        if frame.output_allowed: allowed.append((i,frame.bpm))
        elif frame.bpm is not None: forbidden+=1
    return dict(target_bpm=bpm,input_rows=count,processed_rows=front.slots_emitted,
        algorithm='frozen PeakTimingChain',allowed_rows=len(allowed),forbidden_rows=forbidden,
        first_allowed_sequence=allowed[0][0] if allowed else None,
        max_error_bpm=max(abs(v-bpm) for _,v in allowed) if allowed else None,
        mean_error_bpm=sum(abs(v-bpm) for _,v in allowed)/len(allowed) if allowed else None,
        scope_cn='合成理想输入的实现检查，不是人体准确率或前端跨采样率等价证明。')


def ipc_comparison(count=800):
    observations=list(inputs(72,count))
    bad_first=min(count//3,100)
    for index in (bad_first,bad_first+1):
        observations[index]=replace(observations[index],pair_ok=False)
    warm,warmer=PeakTimingChain(FixedNlmsBackend()),Frontend25()
    for ob in inputs(72,700): warm.step(warmer.push(ob))
    del warm,warmer
    front,chain=Frontend25(),PeakTimingChain(FixedNlmsBackend())
    direct=[]; values=[]; slots=[]
    print('直接25Hz处理回放；预热与正式硬件无关。',flush=True)
    for i,ob in enumerate(observations):
        started=time.perf_counter_ns()
        slot=front.push(ob); result=chain.step(slot)
        direct.append(time.perf_counter_ns()-started); slots.append(asdict(slot)); values.append(asdict(result))
        if (i+1)%250==0: print('  direct 已处理',i+1,'点',flush=True)
    other=Frontend25(); bridge=Bridge25('python_fixed'); bridge.attach_backend(FixedNlmsBackend())
    differences=front_differences=0; isolated=[]
    try:
        bridge.reset()
        print('独立PS进程预热完成；开始同输入逐字段核对。',flush=True)
        for i,ob in enumerate(observations):
            started=time.perf_counter_ns()
            slot=other.push(ob); result=bridge.step(slot)
            isolated.append(time.perf_counter_ns()-started)
            front_differences+=int(slots[i]!=asdict(slot))
            differences+=int(values[i]!=asdict(result))
            if (i+1)%250==0: print('  isolated 已核对',i+1,'点',flush=True)
    finally: bridge.close()
    info=bridge.info()
    if info['forced_termination'] or info['exitcode']!=0: raise RuntimeError('PS子进程没有正常收尾')
    mature_first=bad_first+402
    return dict(compared_slots=count,runtime_field_differences=differences,frontend_differences=front_differences,
        invalid_slots=front.audit()['invalid_slots'],direct=distribution(direct),isolated=distribution(isolated),
        direct_mature=distribution(direct[mature_first:]),isolated_mature=distribution(isolated[mature_first:]),
        mature_first_sequence=mature_first,direct_warmup_slots=700,
        direct_over_40ms=sum(v>40_000_000 for v in direct),isolated_over_40ms=sum(v>40_000_000 for v in isolated),
        budget_period_ms=40,worker_hardware_imported=info['worker_hardware_imported'],isolation=info,
        live_25hz_passed=False,scope_cn='前端+完整PS+软件NLMS与进程桥墙钟；不含IIC、真实PL、持续落盘或显示竞争。')


def run_checks():
    if any(n=='pynq' or n.startswith('pynq.') for n in sys.modules):
        raise RuntimeError('只读检查不能混入已加载硬件的内核')
    cases=[]
    for bpm in (72,120,180):
        print('合成心率检查：',bpm,'BPM；800点。',flush=True)
        cases.append(synthetic_case(bpm))
    comparison=ipc_comparison()
    good=all(c['allowed_rows']>100 and c['forbidden_rows']==0 and c['max_error_bpm'] is not None
             and c['max_error_bpm']<3 for c in cases)
    good &= comparison['runtime_field_differences']==comparison['frontend_differences']==0
    return dict(schema='effective25_software_check_v1',**FLAGS,hardware_loaded=False,board_tested=False,
        python=sys.version,machine=platform.machine(),raw_hz=25,processing_hz=25,adc_hz=50,
        implementation_checks_passed=bool(good),synthetic_cases=cases,ipc=comparison,
        antialias=average2_response(),scope_cn='无硬件检查；实现通过不等于实时、数值跨前端等价或人体准确率验收。')
