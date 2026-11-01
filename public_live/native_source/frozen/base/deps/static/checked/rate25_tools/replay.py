"""Replay immutable integer packets, saving complete replies before comparison."""
import csv

from heart_v3a.axi_contract import NlmsPacket, BETA_DEFAULT
from .data import load_cases
from .delivery import validate
from .reporting import output_directory, save, header


def new_report(root):
    report = header(root, 'v3a25_pl_replay_v1')
    report.update(public_replay_passed=False, board_pl25_replay_passed=False,
                  attempted=0, received=0, checked=0, cases=[], stage='start', sequence=None,
                  scope_cn='仅固定整数25Hz输入的NLMS公开结果回放；非实采/显示/准确率/DDR验收。')
    return report


def replay_into(driver, cases, directory, report):
    fields = ('case','sequence','epoch','beta_int','candidate_int','output_int','status','latency_cycles')
    with (directory/'actual25.csv').open('x', encoding='utf8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        stream.flush()
        for case in cases:
            report['stage'] = case['name']+'/reset'
            report['sequence'] = None
            epoch = driver.reset()
            delays, clipped, saturated = [], 0, 0
            for index, vector in enumerate(case['vectors']):
                p, expected = vector['packet'], vector['reply']
                packet = NlmsPacket(**{**p, 'references':tuple(p['references'])})
                if packet.sequence != index or packet.beta_int != BETA_DEFAULT:
                    raise ValueError('向量序号／固定beta不符')
                report['stage'], report['sequence'] = case['name']+'/transact', index
                report['attempted'] += 1
                reply = driver.transact(packet)
                report['received'] += 1
                row = dict(case=case['name'], **{k:getattr(reply,k) for k in fields if k != 'case'})
                writer.writerow(row)
                stream.flush()
                report['stage'] = case['name']+'/compare'
                if (reply.sequence, reply.epoch, reply.beta_int, reply.candidate_int, reply.output_int, reply.status) != (
                    index, epoch, BETA_DEFAULT, expected['candidate_int'], expected['output_int'], expected['status']):
                    raise RuntimeError('公开PL结果与新25Hz向量不符')
                if not 0 < reply.latency_cycles <= 2048:
                    raise RuntimeError('PL核心周期超出契约')
                delays.append(reply.latency_cycles)
                clipped += bool(reply.status & 4)
                saturated += bool(reply.status & 8)
                report['checked'] += 1
            report['stage'] = case['name']+'/snapshot'
            counts = driver.snapshot()
            n = len(case['vectors'])
            if (counts['accepted'],counts['emitted'],counts['clipped'],counts['saturated'],counts['epoch']) != (n,n,clipped,saturated,epoch):
                raise RuntimeError('PL累计计数不符')
            if counts['max_latency_cycles'] != max(delays): raise RuntimeError('PL最大周期不符')
            report['cases'].append(dict(name=case['name'],samples=n,epoch=epoch,counts=counts,
                                       min_latency_cycles=min(delays),max_latency_cycles=max(delays)))
            print(case['name']+'：完整核对'+str(n)+'槽。', flush=True)
    report['public_replay_passed'] = report['checked'] == sum(len(c['vectors']) for c in cases)
    report['stage'], report['sequence'] = 'complete', None


def record_error(report, exc, driver=None):
    report['error'] = dict(stage=report['stage'], sequence=report['sequence'],
                           type=type(exc).__name__, message=str(exc),
                           backend_fault=getattr(driver, '_fault', '') if driver is not None else '')


def run(root, driver, output=None):
    """Supplied-driver engine. Only hardware.run may declare physical board use."""
    validate(root)
    directory = output_directory(root, output, 'pl25-software-boundary')
    report = new_report(root)
    try:
        replay_into(driver, load_cases(root), directory, report)
    except (Exception, KeyboardInterrupt) as exc:
        record_error(report, exc, driver)
    save(directory, 'pl25.json', report)
    return report
