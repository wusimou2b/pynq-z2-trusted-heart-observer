"""Manual real joint60, unchanged Lean run with bounded exit-only observation."""
from functools import partial
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
if __package__:
    from .joint_exit_guard import verify_package, verify_evidence, write_new
    from .joint_exit_worker import start_owner, describe
    from .joint_exit_report import collect, export, text_report
    from .joint_startup import replace_attribute
    from . import ps_exit_trace as trace_api, ps_exit_finalizing as state_api
else:
    from joint_exit_guard import verify_package, verify_evidence, write_new
    from joint_exit_worker import start_owner, describe
    from joint_exit_report import collect, export, text_report
    from joint_startup import replace_attribute
    import ps_exit_trace as trace_api, ps_exit_finalizing as state_api

ROOT = Path(__file__).resolve().parent


def readiness(root, *, hardware=False):
    evidence = verify_evidence(root, root.parent/'v3b25 native100 heart video', hardware=hardware)
    return dict(evidence=evidence, runtime=trace_api.verify_runtime(), query=state_api.verify_query())


def prepare():
    root = ROOT
    if (root/'joint-exit60-ready.json').exists():
        raise FileExistsError('已有准备记录，保留；不重复运行第一单元')
    ready = readiness(root)
    write_new(root/'joint-exit60-ready.json', ready)
    print('已复用原短测和1505点普通回放证明；没有运行新短测或访问硬件。', flush=True)
    return ready


def run(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-JOINT-EXIT60':
        raise ValueError('explicit hardware=True and RUN-JOINT-EXIT60 required')
    root = ROOT
    if any((root/n).exists() for n in ('joint-exit60-attempt.json','joint-exit60.json',
            'joint-exit60-results.zip','lean-ps-live-attempt.json','native-heart-results.zip')):
        raise FileExistsError('已有本次尝试或结果，保留，不覆盖/自动重试')
    ready = readiness(root, hardware=True)
    if ready != json.loads((root/'joint-exit60-ready.json').read_text('utf-8')):
        raise ValueError('准备后来源/运行时改变；不启动采集')
    if __package__:
        from . import run_lean_ps as original, lean_ps_worker as worker
    else:
        import run_lean_ps as original, lean_ps_worker as worker
    prepared = ready['evidence']['prepared']
    source = root.parent/'v3b25 native100 heart video'
    exits, states, owners = trace_api.make_shared(), state_api.make_shared(), []
    # The unchanged original gate has already validated the OLD root above.
    # Only this scoped alias supplies that same report to the unchanged run.
    def retained_short(requested, current):
        if Path(requested).resolve() != root or current != prepared:
            raise ValueError('mixed root/prepared identity at retained short gate')
        return ready['evidence']['evidence']['short']
    write_new(root/'joint-exit60-attempt.json', dict(ready=ready, automatic_retry=False))
    failure, result = None, None
    try:
        with replace_attribute(original, 'ROOT', root), \
             replace_attribute(original, 'require_short', retained_short), \
             replace_attribute(worker, 'start_owner', partial(start_owner, root=root, source=source,
                               exits=exits, states=states, owners=owners)):
            result = original.run_live(hardware=True, confirmation='RUN-LEAN-PS60')
    except BaseException as exc:
        failure = exc
    identity_error = None
    try:
        if readiness(root, hardware=True) != ready:
            raise ValueError('原来源/退出观察运行时在采集期间改变')
    except Exception as exc:
        identity_error = describe(exc)
    report = collect(root, exits, states, owners,
        original_error=describe(failure) if failure is not None else None, identity_error=identity_error)
    report['original_candidate_pilot_completed'] = bool(result and result.get('joint_60s_pilot_completed'))
    try:
        export(root, report)
    except BaseException as exc:
        print('附加退出报告导出失败，保留原结果/目录：'+str(exc), flush=True)
        if failure is not None:
            raise failure from exc
        raise
    print(text_report(report), flush=True)
    from IPython.display import display, FileLink
    display(FileLink('joint-exit60-results.zip'))
    if failure is not None:
        raise failure
    return report


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check-bundle', action='store_true', required=True)
    p.parse_args()
    print(json.dumps(verify_package(ROOT), ensure_ascii=False))
