"""Read fixed exit tables only after actual owner and PS exit proof."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

if __package__:
    from .joint_exit_guard import sha, write_new
    from .ps_exit_trace import snapshot, analyze
    from .ps_exit_finalizing import snapshot as state_snapshot
else:
    from joint_exit_guard import sha, write_new
    from ps_exit_trace import snapshot, analyze
    from ps_exit_finalizing import snapshot as state_snapshot

_retained = []


def owner_states(owners, saved):
    result = []
    for r in owners:
        p = r['process']
        row = dict(pid=r['pid'], exitcode=None, exited=False, evidence='unknown')
        try:
            row.update(pid=p.pid, exitcode=p.exitcode)
            row['exited'] = bool(type(row['pid']) is int and type(row['exitcode']) is int and not p.is_alive())
            row['evidence'] = 'actual_process_handle'
        except ValueError as exc:
            if (str(exc) == 'process object is closed' and type(r['pid']) is int
                and saved.get('owner_pid') == r['pid'] and type(saved.get('owner_exitcode')) is int):
                row.update(exitcode=saved['owner_exitcode'], exited=True, evidence='matching_original_saved_exit')
        result.append(row)
    return result


def collect(root, exits, states, owners, *, original_error=None, identity_error=None):
    root = Path(root).resolve()
    reports, errors, owner_report = {}, [], None
    parent = child = finalizing = None
    try:
        with ZipFile(root/'native-heart-results.zip') as z:
            if len(z.namelist()) != len(set(z.namelist())) or z.testzip() is not None:
                raise ValueError('original Native ZIP corrupt')
            for n in ('capture/summary.json','run_effective25_display.json','concurrent_owner_result.json'):
                if n in z.namelist():
                    reports[n] = json.loads(z.read(n))
    except Exception as exc:
        errors.append(dict(stage='original_reports', type=type(exc).__name__, message=str(exc)))
    statuses = owner_states(owners, reports.get('run_effective25_display.json') or {})
    owner_proven = bool(statuses) and all(r['exited'] for r in statuses)
    ps_proven = False
    if owner_proven and len(owners) == 1:
        try:
            path = Path(owners[0]['directory']).resolve()/'owner_joint_exit.json'
            if not path.is_relative_to(root) or path.is_symlink():
                raise ValueError('owner observation path escaped')
            owner_report = json.loads(path.read_text('utf-8'))
            bridges = owner_report['bridges']
            if owner_report['owner_pid'] != statuses[0]['pid'] or len(bridges) != 1:
                raise ValueError('actual owner/bridge identity differs')
            b = bridges[0]
            info = b.get('info') or {}
            ps_proven = bool(b['exited'] and type(b['pid']) is int and type(b['exitcode']) is int
                and info.get('exitcode') == b['exitcode'] and info.get('cleanup_complete') is True)
            if not ps_proven:
                raise ValueError('actual PS exit unproven; trace unread')
            parent = analyze(snapshot(exits, 'parent'))
            child = analyze(snapshot(exits, 'child'))
            finalizing = state_snapshot(states, child)
            if parent['pid'] != owner_report['owner_pid'] or child['pid'] != b['pid']:
                raise ValueError('exit table PID mismatch')
            if (parent['errors'] or child['errors'] or not finalizing['complete']
                or owner_report['observation_errors'] or b['observation_errors']):
                raise ValueError('exit observer incomplete/errors')
        except Exception as exc:
            errors.append(dict(stage='exit_proof_or_trace', type=type(exc).__name__, message=str(exc)))
    else:
        errors.append(dict(stage='owner_exit', message='actual owner exit unproven; trace unread'))
    if not owner_proven or not ps_proven:
        _retained.append((exits, states, owners))
    if identity_error:
        errors.append(dict(stage='post_identity', **identity_error))
    actual = reports.get('concurrent_owner_result.json') or {}
    hardware_clean = bool(actual.get('inherited_cleanup_complete') is True
        and (actual.get('video_cleanup') or {}).get('cleanup_complete') is True
        and actual.get('actual_lease_released') is True and actual.get('quarantine_required') is False
        and actual.get('retention_reasons') == [])
    summary = reports.get('capture/summary.json') or {}
    isolation = summary.get('isolation') or {}
    natural = bool(isolation.get('cleanup_complete') is True and isolation.get('forced_termination') is False
                   and isolation.get('exitcode') == 0)
    marker = bool(child and any(r['event'] in ('delegate_returned','delegate_error') for r in child['rows']))
    return dict(schema='v3b25_joint_exit60_observation_v1',
        observation_complete=bool(owner_proven and ps_proven and parent and parent['rows'] and marker
                                  and not errors and hardware_clean),
        owner_exited=owner_proven, ps_exit_proven=ps_proven, owners=statuses, owner_observation=owner_report,
        parent=parent, child=child, finalizing=finalizing, errors=errors, original_error=original_error,
        original_ps_natural_exit=natural, original_ps_forced_termination=isolation.get('forced_termination'),
        original_ps_exitcode=isolation.get('exitcode'), hardware_cleanup_confirmed=hardware_clean,
        formal_elapsed_seconds=summary.get('elapsed_seconds'), processed=summary.get('processed'),
        original_fault=summary.get('fault'), original_lean_zip_sha256=sha(root/'lean-ps-live-results.zip')
            if (root/'lean-ps-live-results.zip').is_file() else None,
        gc_strategy_changed=False, join_timeout_changed=False, accuracy_verified=False,
        strict_realtime_verified=False, board_ddr_verified=False, full_v3b_acceptance_passed=False)


def text_report(r):
    return '\n'.join(['Lean25/25Hz＋5fps联合60秒退出观测（不是修复或完整验收）',
        '退出观测完整：'+str(r['observation_complete']), '原PS自然退出：'+str(r['original_ps_natural_exit']),
        '原forced / exitcode：%s / %s'%(r['original_ps_forced_termination'],r['original_ps_exitcode']),
        '原故障：'+str(r['original_fault']), '原异常：'+str(r['original_error']),
        '观测异常：'+str(r['errors']), '硬件收尾确认：'+str(r['hardware_cleanup_confirmed']),
        '原1秒join/terminate/join、GC/700点/采集/视频/算法不变，失败不重试。',
        '父端只记录实际关闭线程；子端退出记录有分配/调度扰动，finalizing不是模块清理完成。'])+'\n'


def export(root, report):
    root = Path(root)
    write_new(root/'joint-exit60.json', report)
    with (root/'joint-exit60.txt').open('x', encoding='utf-8') as f:
        f.write(text_report(report))
    with ZipFile(root/'joint-exit60-results.zip', 'x', compression=ZIP_DEFLATED) as z:
        for n in ('joint-exit60.json','joint-exit60.txt','joint-exit60-ready.json','lean-ps-live-results.zip',
                  'proofs/lean-ps-short-results.zip','proofs/lean-exit-plain-results.zip'):
            if (root/n).is_file():
                z.write(root/n, n)
