"""Same-input PS budget with recorded replies; never imports or calls PYNQ."""
from dataclasses import asdict, replace
import sys
import time

import numpy as np
import scipy
from heart_v3a.axi_contract import NlmsReply
from v3a_rate25.frontend import RawFrontend
from peak_chain import PeakTimingChain
from v3a_25hz_live.bridge import ProcessChain25
from v3a_25hz_live.safety import RawSafety
from .data import canonical, load_cases, reference
from .delivery import validate
from .reporting import output_directory, save, header, distribution


class RecordedBackend:
    source = 'python_fixed'

    def __init__(self, vectors):
        self.vectors, self.index, self.epoch = vectors, 0, 0

    def reset(self):
        if self.epoch: raise RuntimeError('记录回复后端只能初始化一次')
        self.epoch = 1
        return self.epoch

    def transact(self, packet):
        if self.index >= len(self.vectors) or canonical(packet) != self.vectors[self.index]['packet']:
            raise ValueError('提交包与绑定向量不符／重复')
        row = self.vectors[self.index]
        self.index += 1
        return replace(NlmsReply(**row['reply']), epoch=self.epoch)


def prepare_case(case):
    prepared = reference(case['observations'])
    if prepared['vectors'] != case['vectors']:
        raise ValueError('本机25Hz整数向量与交付不符，禁止继续测量或硬件回放')
    return prepared


def measure(case, prepared, *, isolated):
    mode = 'isolated' if isolated else 'direct'
    backend = RecordedBackend(prepared['vectors'])
    front, safety = RawFrontend(), RawSafety()
    chain = None
    rows, raw_ns = [], []
    info = None
    try:
        if isolated:
            chain = ProcessChain25('python_fixed')
            chain.attach_backend(backend)
            chain.reset()
        else:
            chain = PeakTimingChain(backend)
        for i, ob in enumerate(case['observations']):
            started = time.perf_counter_ns()
            safety.observe(ob, i*20_000_000)
            slot = front.push(ob)
            raw_ns.append(time.perf_counter_ns()-started)
            state = safety.snapshot()
            if (state.generation,state.contact_ready) != (front.generation,front.contact_ready):
                raise ValueError('原始安全快路与前端不一致')
            if slot is None: continue
            started = time.perf_counter_ns()
            runtime = chain.step(slot)
            ps_ns = time.perf_counter_ns()-started
            if asdict(runtime) != asdict(prepared['frames'][slot.sequence]):
                raise ValueError('同输入PS结果字段不一致：'+str(slot.sequence))
            pair_ns = raw_ns[-2]+raw_ns[-1]
            rows.append(dict(sequence=slot.sequence,raw_first=slot.source_sequences[0],raw_last=slot.source_sequences[1],
                             raw_front_ns=pair_ns,ps_ns=ps_ns,pair_total_ns=pair_ns+ps_ns))
            if len(rows)%250 == 0:
                print(f"{case['name']} / {mode}：已核对{len(rows)}槽", flush=True)
    finally:
        if isolated and chain is not None:
            chain.close()
            info = chain.info()
            if not info['cleanup_complete'] or info['forced_termination'] or info['exitcode'] != 0:
                raise RuntimeError('预算进程未自然退出：'+str(info))
    if backend.index != len(prepared['vectors']): raise ValueError('记录回复消费不完整')
    return dict(rows=rows, raw_front_each_ns=raw_ns, frontend=front.audit(), isolation=info,
                all_pair=distribution([r['pair_total_ns'] for r in rows]),
                mature_pair=distribution([r['pair_total_ns'] for r in rows[200:]]),
                mature_ps=distribution([r['ps_ns'] for r in rows[200:]]),
                mature_from_slot=200)


def run(root, output=None):
    validate(root)
    directory = output_directory(root, output, 'budget25')
    report = header(root, 'v3a25_budget_v1')
    report.update(budget_report_complete=False, numpy=np.__version__, scipy=scipy.__version__, cases=[],
        scope_cn='只读已有输入，记录回复替代PL；无IIC/持续落盘/显示竞争。准备与预热另计，非实时或准确率验收。',
        timing_scope_cn='原始安全+FIR双点耗时与槽PS调用墙钟顺序相加；PS包含记录回复/IPC，非纯CPU或真实PL。')
    stage = 'inputs'
    try:
        for case in load_cases(root):
            stage = case['name']+'/prepare'
            print(stage+'：纯软件参考准备，不计入预算。', flush=True)
            started = time.monotonic()
            prepared = prepare_case(case)
            item = dict(name=case['name'],raw_count=len(case['observations']),
                        prepare_seconds=time.monotonic()-started,packaged_vectors_match=True,runtime_differences=0)
            report['cases'].append(item)
            for mode in ('direct','isolated'):
                stage = case['name']+'/'+mode
                print(stage+'：开始；独立进程预热另计。', flush=True)
                item[mode] = measure(case, prepared, isolated=mode=='isolated')
        if any(n == 'pynq' or n.startswith('pynq.') for n in sys.modules):
            raise RuntimeError('只读检查中发现硬件模块导入')
        report['budget_report_complete'] = True
    except (Exception, KeyboardInterrupt) as exc:
        report['error'] = dict(stage=stage,type=type(exc).__name__,message=str(exc))
    report['module_paths'] = {name:str(sys.modules[name].__file__) for name in
        ('heart_v2.runtime_main_chain','heart_v3a.live.process_chain','v3a_rate25.frontend','peak_chain',
         'v3a_25hz_live.bridge','rate25_tools.budget') if name in sys.modules}
    save(directory, 'budget25.json', report)
    print('报告：'+str(directory/'budget25.json'), flush=True)
    return report
