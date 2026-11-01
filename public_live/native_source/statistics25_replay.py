"""Same-input full PS computation proof and ABBA timing; no hardware or IPC."""
from dataclasses import asdict, is_dataclass
import hashlib
import json
import math
from pathlib import Path
import platform
import struct
import sys
import time

if __package__:
    from . import ps_budget_runtime as original
    from .ps_budget_guard import differences
    from .statistics25_core import make_candidate
else:
    import ps_budget_runtime as original
    from ps_budget_guard import differences
    from statistics25_core import make_candidate


def _classes(source, host_check):
    deps = original.load_runtime(Path(source)/'frozen')
    api = make_candidate()
    native = sys.platform == 'linux' and platform.machine() == 'armv7l'
    if not native and not host_check:
        raise RuntimeError('仅ARM运行；电脑验证必须显式--host-check')
    saved = json.loads((Path(source)/'frozen/provenance/entry25_board_check.json').read_text())['native_sos_hex']
    sections = tuple(tuple(float.fromhex(v) for v in row) for row in saved)
    if native:
        detector = deps.Chain(deps.Fixed()).output_detector
        if detector._sections != sections:
            raise ValueError('当前ARM原生SOS系数与原板端确认值不符，停止，不替换系数')
        classes = deps.Chain, api.Chain
    else:
        # Explicit host-only reproduction of saved ARM constants. Never used
        # on ARM and never written into the original classes or source files.
        def bind(base):
            class HostChain(base):
                def _reset_signals(self):
                    super()._reset_signals()
                    for detector in [*self.detectors.values(), self.output_detector]:
                        detector._sections = sections
            return HostChain
        classes = bind(deps.Chain), bind(api.Chain)
    return deps, api, classes, native


def _bits(value):
    import numpy as np
    if is_dataclass(value): return _bits(asdict(value))
    if isinstance(value, np.ndarray):
        return [value.dtype.str, list(value.shape), value.tobytes().hex()]
    if isinstance(value, dict): return {k:_bits(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [_bits(v) for v in value]
    if isinstance(value, (float,np.floating)): return struct.pack('>d',float(value)).hex()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, bytes): return value.hex()
    return value


def _fingerprint(value):
    return hashlib.sha256(json.dumps(_bits(value),ensure_ascii=False,sort_keys=True,
                                     separators=(',',':')).encode()).hexdigest()


def _tracked(base, cache_base, selector_base, assess):
    from heart_v3a.live.numpy_compat import _bind
    log = dict(quality=[],history=[])
    class Cache(cache_base):
        def get(self, values):
            result = super().get(values)
            log['quality'].append(_fingerprint((values,result,list(self.entries))))
            return result
    def tracked_assess(*args):
        result = assess(*args)
        log['history'].append(_fingerprint((args,result)))
        return result
    class Selector(selector_base):
        step = _bind(selector_base.step, assess_history25=tracked_assess)
    class Chain(base):
        def _reset_signals(self):
            super()._reset_signals()
            cache = Cache()
            for component in self.quality_components.values(): component.window_cache = cache
            self.selector = Selector()
    return Chain, log


def _walk(deps, chain_class, obs, rows, *, timed=False, emit=print):
    chain, front = chain_class(deps.Fixed()), deps.Frontend()
    report = dict(count=0,difference_count=0,first_differences=[],samples=[])
    hasher = hashlib.sha256()
    for i,(ob,row) in enumerate(zip(obs,rows)):
        if timed: w0=time.perf_counter_ns(); c0=time.process_time_ns()
        slot=front.push(ob); runtime=chain.step(slot)
        if timed:
            c1=time.process_time_ns();w1=time.perf_counter_ns()
            report['samples'].append(dict(sequence=i,wall_ns=w1-w0,cpu_ns=c1-c0))
        values=original.values(slot,runtime)
        delta=differences(row,values)
        report['difference_count']+=len(delta)
        report['first_differences'].extend(delta[:max(0,12-len(report['first_differences']))])
        hasher.update(json.dumps(values,ensure_ascii=False,sort_keys=True,
                                separators=(',',':'),allow_nan=False).encode()+b'\n')
        report['count']+=1
        if (i+1)%250==0:emit('已核对 %d/%d 点'%(i+1,len(rows)),flush=True)
    report.update(runtime_sha256=hasher.hexdigest(),frontend=front.audit())
    if timed:
        samples=report['samples'];wall=[s['wall_ns'] for s in samples]
        report.update(total_wall_ns=sum(wall),total_cpu_ns=sum(s['cpu_ns'] for s in samples),
                      worst_five_wall_ns=max(sum(wall[i:i+5]) for i in range(len(wall)-4)),
                      final_four_wall_ns=sum(wall[-4:]))
    return report


def qualify(source, data, *, host_check=False, emit=print):
    deps,api,classes,native=_classes(source,host_check)
    from v3a_rate25.state import QualityCache25
    from v3a_rate25.benefit import assess_history25
    from entry25_candidate import DelayedSelector25
    obs=original.observations(deps,data['raw'])
    old,old_log=_tracked(classes[0],QualityCache25,DelayedSelector25,assess_history25)
    new,new_log=_tracked(classes[1],api.QualityCache,api.Selector,api.assess_history)
    emit('严格核对参考原链；所有1504点及四个无效slot均保留。',flush=True)
    a=_walk(deps,old,obs,data['results'],emit=emit)
    emit('严格核对候选原链与所有实际统计窗口。',flush=True)
    b=_walk(deps,new,obs,data['results'],emit=emit)
    same=old_log==new_log
    return dict(reference=a,candidate=b,statistics_exact=same,
                quality_calls=len(old_log['quality']),history_calls=len(old_log['history']),
                statistics_sha256=_fingerprint(old_log),candidate_statistics_sha256=_fingerprint(new_log),
                arm_native=native,host_arm_coefficients_bound=not native,
                passed=(a['count']==b['count']==1504 and a['difference_count']==b['difference_count']==0
                        and a['runtime_sha256']==b['runtime_sha256'] and same
                        and len(old_log['quality'])>0 and len(old_log['history'])>0))


def _warmup(deps, chain_class):
    from heart_v2.runtime_main_chain import Observation
    start=time.perf_counter_ns();chain=chain_class(deps.Fixed());front=deps.Frontend()
    for i in range(700):
        chain.step(front.push(Observation(i,i/25.,125000+600*math.sin(2*math.pi*1.2*i/25.),(0.,0.,1.),True)))
    return time.perf_counter_ns()-start


def timing_gate(groups):
    structure=len(groups)==4 and [g['mode'] for g in groups]==list('ABBA')
    a=[g for g in groups if g['mode']=='A']; b=[g for g in groups if g['mode']=='B']
    if not structure:return dict(passed=False,structure=False)
    old=sum(g['total_wall_ns'] for g in a)/2; new=sum(g['total_wall_ns'] for g in b)/2
    checks=dict(structure=True,complete=all(g['count']==1504 and g['difference_count']==0 for g in groups),
                reduction_at_least_10_percent=new<=old*.9,
                each_candidate_lower=all(g['total_wall_ns']<old for g in b),
                worst_five_not_worse=max(g['worst_five_wall_ns'] for g in b)<=max(g['worst_five_wall_ns'] for g in a))
    return dict(checks=checks,reference_mean_wall_ns=old,candidate_mean_wall_ns=new,
                reduction_fraction=1-new/old,passed=all(checks.values()))


def measure(source, data, proof, *, host_check=False, emit=print):
    if not proof['passed']:raise ValueError('strict proof failed; no performance run')
    deps,api,classes,native=_classes(source,host_check)
    obs=original.observations(deps,data['raw'])
    emit('参考/候选各700点预热另计；不改GC，不启IPC或硬件。',flush=True)
    warm=[_warmup(deps,cls) for cls in classes]
    groups=[]
    for index,mode in enumerate('ABBA'):
        emit('完整计算链第%d/4遍：%s；不包含IIC/真实PL/IPC/落盘/视频。'%(index+1,mode),flush=True)
        group=_walk(deps,classes[mode=='B'],obs,data['results'],timed=True,emit=emit)
        group['mode']=mode;groups.append(group)
        if group['runtime_sha256']!=proof['reference']['runtime_sha256'] or group['difference_count']:
            raise ValueError('timed run numerical identity changed')
    return dict(warmup_slots=700,warmup_wall_ns=warm,groups=groups,gate=timing_gate(groups),arm_native=native)
