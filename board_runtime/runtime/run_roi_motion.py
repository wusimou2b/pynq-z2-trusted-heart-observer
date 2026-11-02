"""Cold manual launcher; never kill a video worker retaining hardware ownership."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
from zipfile import ZipFile, ZIP_DEFLATED

PENDING_CHILDREN = []


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as sink:
        json.dump(value, sink, ensure_ascii=False, indent=2, allow_nan=False)


def verify(root):
    if __package__:
        from .roi_motion_guard import verify_package
    else:
        from roi_motion_guard import verify_package
    return verify_package(root)


def supervise(child, root, *, startup_seconds=180, stop_wait=10, poll_seconds=.25, show=lambda:None):
    root = Path(root); began = time.monotonic(); ready_seen = None
    reason = None
    try:
        while child.poll() is None:
            now = time.monotonic()
            if (root/'formal-ready.json').exists() and ready_seen is None:
                ready_seen = now
            if ready_seen is None and now-began >= startup_seconds:
                reason = 'startup_timeout'; break
            # Formal60 plus original10s thread-stop allowance and bounded hardware close;
            # this is a wait budget, never permission to kill or release active buffers.
            if ready_seen is not None and now-ready_seen > 90:
                reason = 'formal_or_cleanup_wait_timeout'; break
            try:child.wait(timeout=poll_seconds)
            except subprocess.TimeoutExpired:pass
            show()
    except KeyboardInterrupt:
        reason = 'parent_interrupted'
    if child.poll() is None:
        if not (root/'stop.request').exists():write_new(root/'stop.request', dict(reason=reason))
        try:child.wait(timeout=stop_wait)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):pass
    show()
    return dict(pid=child.pid, worker_exited=child.poll() is not None, exitcode=child.poll(),
        startup_timed_out=reason == 'startup_timeout', stop_reason=reason,
        cleanup_unconfirmed=child.poll() is None, child_force_terminated=False)


def worker(root):
    verify(root)
    if sys.platform != 'linux' or platform.machine() != 'armv7l':
        raise RuntimeError('board ARM Linux only')
    # Heavy imports start only in the authorized single hardware-owner process.
    try:
        from roi_motion_runtime import run_session
    except BaseException as exc:
        (root/'results').mkdir(exist_ok=False)
        retained = None
        report = dict(schema='v3b25_roi_motion_calibration_run_v1', session_complete=False,
            fault=dict(stage='runtime_import', type=type(exc).__name__, message=str(exc)),
            calibration=dict(profile_ready=False, reason='runtime import failed'),
            cleanup=dict(cleanup_complete=True, quarantine_required=False, hardware_open_not_attempted=True),
            heart_capture_started=False, heart_ps_started=False, imu_capture_started=False,
            independent_validation_passed=False, full_v3b_acceptance_passed=False, board_ddr_verified=False)
    else:
        report, retained = run_session(root, root/'results')
    try:
        verify(root); report['inputs_unchanged'] = True
    except BaseException as exc:
        report['inputs_unchanged'] = False; report['post_identity_error'] = str(exc)
        report['session_complete'] = False
    try:
        write_new(root/'results/report.json', report)
        with ZipFile(root/'roi-motion-results.zip', 'x', compression=ZIP_DEFLATED) as archive:
            for path in sorted((root/'results').iterdir()):
                if path.is_file():archive.write(path, path.name)
            if (root/'roi-motion-manifest.json').is_file():
                archive.write(root/'roi-motion-manifest.json', 'roi-motion-manifest.json')
        print('60秒会话完整：', report['session_complete'], '；可运行标定阈值：', report['calibration']['profile_ready'], flush=True)
        print('请回传 roi-motion-results.zip；实际画面与执行动作仍需你确认。', flush=True)
    finally:
        if retained is not None:
            print('QUARANTINE：停止未确认，保留所有者/缓冲/锁；不要关闭或重跑。', flush=True)
            while True:time.sleep(1)
    return 0 if report['session_complete'] and report['calibration']['profile_ready'] else 1


def launch_once(root, *, confirmation):
    root = Path(root).resolve(); verify(root)
    if confirmation != 'RUN-ROI-CALIBRATION':raise ValueError('manual hardware confirmation required')
    if sys.platform != 'linux' or platform.machine() != 'armv7l':raise RuntimeError('board ARM Linux only')
    for name in ('attempt.json', 'results', 'video.log', 'stop.request', 'roi-motion-results.zip', 'formal-ready.json'):
        if (root/name).exists():raise FileExistsError('attempt/result exists; preserve, do not retry')
    write_new(root/'attempt.json', dict(started_monotonic_ns=time.monotonic_ns()))
    with (root/'video.log').open('xb') as log:
        child = subprocess.Popen([sys.executable, '-B', '-u', str(root/'run_roi_motion.py'), '--worker'],
            cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        PENDING_CHILDREN.append(child)
        write_new(root/'child.json', dict(pid=child.pid))
        position = 0
        def show():
            nonlocal position
            with (root/'video.log').open('rb') as source:
                source.seek(position); data = source.read(); position = source.tell()
            if data:print(data.decode('utf-8', errors='replace'), end='', flush=True)
        status = supervise(child, root, show=show)
        if status['worker_exited']:PENDING_CHILDREN.remove(child)
        else:print('收尾未确认：未强杀，不重试，保持本页面与内核。', flush=True)
    status['archive_exists'] = (root/'roi-motion-results.zip').is_file()
    write_new(root/'launch-result.json', status)
    return status


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-bundle', action='store_true'); mode.add_argument('--worker', action='store_true')
    args = parser.parse_args(); root = Path(__file__).resolve().parent
    if args.check_bundle:
        print(json.dumps(verify(root), ensure_ascii=False)); raise SystemExit(0)
    raise SystemExit(worker(root))
