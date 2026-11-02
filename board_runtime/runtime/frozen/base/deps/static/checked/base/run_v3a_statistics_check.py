"""板端只读核验：新旧完整PS等价及成熟窗口计时，不加载Overlay。"""
import argparse
from collections import deque
from dataclasses import asdict, is_dataclass
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

import numpy as np
import scipy

from heart_v2.preprocess import CausalDcBlocker
from heart_v2.runtime_main_chain import Observation
from heart_v2.runtime_state import MotionClassifier, BranchQuality
from heart_v3a.live import history_fast, statistics_fast
from heart_v3a.live.single_sample import ScalarSosHeartRateDetector
from heart_v3a.live.processing import ReusingRuntimePlMainChain as CandidateChain
from heart_v3a.runtime_backend import FixedNlmsBackend
from heart_v3a.runtime_pl_chain import RuntimePlMainChain
from run_v3a_history_check import window_cases, differing_field


class ReferenceChain(RuntimePlMainChain):
    """本轮优化前的独立组件组合，不使用新统计组件作为参照。"""
    step = history_fast.runtime_step

    def _reset_signals(self):
        prep = self.config['preprocess']
        self.ppg_dc = CausalDcBlocker(prep['ppg_dc_alpha'])
        self.ref_dc = [CausalDcBlocker(prep['reference_dc_alpha']) for _ in range(4)]
        self.mean_window = deque(maxlen=4)
        self.selector = history_fast.FastJointBenefitSelector()
        self.motion_classifier = MotionClassifier()
        parameters = self.config['heartrate']
        configuration = tuple(sorted(parameters.items()))
        if getattr(self, '_heartrate_configuration', None) != configuration:
            self.detectors = {key: ScalarSosHeartRateDetector(50., **parameters)
                              for key in ('raw','mean','nlms','joint')}
            self.output_detector = ScalarSosHeartRateDetector(50., **parameters)
            self._heartrate_configuration = configuration
        else:
            for detector in self.detectors.values():
                detector.reset()
            self.output_detector.reset()
        self.quality_components = {key: BranchQuality() for key in self.detectors}
        self.previous_route = 'none'


class RecordingBackend(FixedNlmsBackend):
    def __init__(self):
        super().__init__()
        self.records = []

    def transact(self, packet):
        reply = super().transact(packet)
        self.records.append((packet,reply))
        return reply


class ReplyBackend:
    """完整软件回复重放；逐拍核对请求，计时不含软件NLMS或真实PL。"""
    source = 'python_fixed'

    def __init__(self, records):
        self.records = records
        self.index = 0

    def reset(self):
        self.index = 0
        return 1

    def transact(self, packet):
        expected, reply = self.records[self.index]
        if packet != expected:
            raise RuntimeError('只读回放请求与原链不同：'+str(self.index))
        self.index += 1
        return reply


def frozen(value):
    if is_dataclass(value):
        return frozen(asdict(value))
    if isinstance(value,np.ndarray):
        return value.dtype.str,value.shape,value.tobytes()
    if isinstance(value,(float,np.floating)):
        return float(value).hex()
    if isinstance(value,dict):
        return {k:frozen(v) for k,v in value.items()}
    if isinstance(value,(tuple,list,deque)):
        return tuple(frozen(v) for v in value)
    return value


def causal_state(chain):
    def detector(obj):
        return {k:v for k,v in vars(obj).items() if k not in ('_statistics','step')}
    def quality(obj):
        return {k:v for k,v in vars(obj).items() if k not in ('window_cache','_interval_key','_cv')}
    return frozen(dict(gate=vars(chain.gate),previous=chain.previous,previous_valid=chain.previous_valid,
        route=chain.previous_route,ppg_dc=vars(chain.ppg_dc),ref_dc=[vars(v) for v in chain.ref_dc],
        mean_window=chain.mean_window,selector=vars(chain.selector),motion=vars(chain.motion_classifier),
        detectors={k:detector(v) for k,v in chain.detectors.items()},output_detector=detector(chain.output_detector),
        qualities={k:quality(v) for k,v in chain.quality_components.items()},controls=chain._last_controls))


def observations(samples):
    return [Observation(i,i/50.,125000+600*math.sin(2*math.pi*1.2*i/50.),
        (.015*math.sin(i*.11),.012*math.cos(i*.13),1.+.01*math.sin(i*.17)),True) for i in range(samples)]


def distribution(values):
    return dict(count=len(values),mean_ms=statistics.mean(values),median_ms=statistics.median(values),
                maximum_ms=max(values),total_ms=sum(values))


def timed(kind, observations_, records):
    backend = ReplyBackend(records)
    chain = kind(backend)
    chain.reset()
    elapsed = []
    for i,ob in enumerate(observations_):
        start = time.perf_counter_ns()
        result = chain.step(ob)
        elapsed.append((time.perf_counter_ns()-start)/1e6)
        if chain._fault or result.pl_sequence != ob.sequence:
            raise RuntimeError('计时回放故障：'+str(chain._fault))
        if (i+1)%250 == 0:
            print('  已计时',i+1,'点',flush=True)
    if backend.index != len(observations_):
        raise RuntimeError('计时事务数量不符')
    return dict(all=distribution(elapsed),mature=distribution(elapsed[400:]),per_sample_ms=elapsed)


def check(samples=1000,repeats=2):
    if samples <= 400 or repeats < 1:
        raise ValueError('需要完整成熟窗口和至少一轮对照')
    cases = window_cases()
    first = None
    differences = 0
    for name,values in cases:
        field = differing_field(statistics_fast.assess_history(*values),history_fast.assess_history(*values))
        if field:
            first = first or dict(stage='history_window',case=name,field=field)
            differences += 1
    recording = RecordingBackend()
    reference = ReferenceChain(recording)
    candidate = CandidateChain(ReplyBackend(recording.records))
    reference.reset(); candidate.reset()
    source = observations(samples)
    allowed = 0
    print('逐点核对新旧完整PS和因果状态，软件NLMS只在本阶段生成回复。',flush=True)
    for i,ob in enumerate(source):
        expected, actual = reference.step(ob), candidate.step(ob)
        if reference._fault or candidate._fault or frozen(actual) != frozen(expected):
            first = first or dict(stage='frame',sequence=i,reference_fault=reference._fault,candidate_fault=candidate._fault)
            differences += 1
        if causal_state(candidate) != causal_state(reference):
            first = first or dict(stage='causal_state',sequence=i)
            differences += 1
        allowed += bool(expected.frame.output_allowed)
        if (i+1)%250 == 0:
            print('  已核对',i+1,'点',flush=True)
    timing = None
    if differences == 0:
        if allowed == 0:
            raise RuntimeError('对照未覆盖有效输出，不进入计时')
        runs = []
        for repeat in range(repeats):
            for name in (('reference','candidate') if repeat%2==0 else ('candidate','reference')):
                print('计时第',repeat+1,'轮：',name,'；完整回复重放，不计算NLMS。',flush=True)
                result = timed(ReferenceChain if name=='reference' else CandidateChain,source,recording.records)
                runs.append(dict(mode=name,repeat=repeat,**result))
        timing = dict(runs=runs,includes_nlms=False,includes_ipc=False,
            scope_cn='仅完整PS直接执行；合成输入连续窗口400点后单独统计，无采集/IPC/真实PL/写盘/显示负载，不是50Hz实采验收。')
    return dict(schema='v3a_statistics_check_v1',python=sys.version,numpy=np.__version__,scipy=scipy.__version__,
        machine=platform.machine(),history_windows_compared=len(cases),samples_compared=samples,
        state_comparisons=samples,output_allowed_rows=allowed,differences=differences,first_difference=first,
        exact_equivalence_passed=differences==0,timing=timing,hardware_loaded=False,live_50hz_passed=False,
        board_ddr_verified=False,auto_beta_effect_passed=False,v3a_complete=False)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('statistics_check.json'))
    args=parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError('不覆盖已有报告：'+str(args.output))
    from heart_v3a.live_delivery import validate_live_bundle, digest
    bundle=Path(__file__).resolve().parent
    validate_live_bundle(bundle)
    manifest_sha=digest(bundle/'live-manifest.json')
    print('只读新旧统计核验：不放手指、不加载Overlay，请勿同时采集或绘图。',flush=True)
    report=check()
    if any(name=='pynq' or name.startswith('pynq.') for name in sys.modules):
        raise RuntimeError('只读入口不应导入PYNQ')
    validate_live_bundle(bundle)
    if digest(bundle/'live-manifest.json')!=manifest_sha:
        raise RuntimeError('核验期间交付身份改变')
    report.update(bundle_validated=True,live_manifest_sha256=manifest_sha,tool_sha256=digest(Path(__file__)))
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print('等价核对：',report['exact_equivalence_passed'],'；差异：',report['differences'])
    if report['timing']:
        for run in report['timing']['runs']:
            print(run['mode'],'成熟窗口：',run['mature'])
    print('请回传：',args.output.resolve())
    return 0 if report['exact_equivalence_passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
