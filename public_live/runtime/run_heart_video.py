"""Manual recovered heart + PL video. CLI is a cold file check only."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
if __package__:
    from .heart_video_guard import verify_package, assess_candidate, sha, write_new
    from .joint_owner import require_board
    from .joint_startup import replace_attribute
else:
    from heart_video_guard import verify_package, assess_candidate, sha, write_new
    from joint_owner import require_board
    from joint_startup import replace_attribute

ROOT = Path(__file__).resolve().parent


def run_joint60(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-HEART-VIDEO60':
        raise ValueError('requires hardware=True and RUN-HEART-VIDEO60')
    require_board()
    checked = verify_package(ROOT)
    archive = ROOT/'heart-video5-results.zip'
    if any(p.exists() for p in (archive, ROOT/'joint-concurrent-attempt.json',
        ROOT/'joint-concurrent-results.zip', ROOT/'frozen/live_results/joint-concurrent5-static60')):
        raise FileExistsError('已有尝试或结果；保留，不覆盖或重跑')
    if __package__:
        from . import run_joint_concurrent5 as original, joint_concurrent_worker as workers
        from .heart_video_worker import start_owner
        from .run_startup180 import install_startup180
    else:
        import run_joint_concurrent5 as original, joint_concurrent_worker as workers
        from heart_video_worker import start_owner
        from run_startup180 import install_startup180
    print('恢复版心率25/25Hz＋PL视频5fps：全程放稳手指，正式共同60秒。', flush=True)
    print('启动预算180秒，PS700点预热最长60秒；运行期保护不变，不自动重试。', flush=True)
    print('使用原PYNQ IIC，不运行native/handoff或逐拍诊断；HDMI视频，Notebook心率。', flush=True)
    def assess(*a, **kw):
        result = assess_candidate(*a, **kw)
        result['checks']['startup_budget'] = bool(budget['parent_run_calls'] == 1
            and budget['startup_timeout_seconds'] == 180 and budget['parent_bytecode_unchanged']
            and budget['shared_original_globals'] and budget['real_clock_unchanged'])
        result['joint_60s_pilot_completed'] = all(result['checks'].values())
        result['startup_budget'] = dict(budget)
        return result
    with install_startup180(ROOT) as budget, \
            replace_attribute(original, 'verify_concurrent', verify_package), \
            replace_attribute(original, 'assess_concurrent', assess), \
            replace_attribute(workers, 'start_owner', start_owner):
        result = original.run_concurrent60(hardware=True, confirmation='RUN-JOINT-5FPS60')
    original_zip = ROOT/'joint-concurrent-results.zip'
    if not original_zip.is_file(): raise RuntimeError('原结果ZIP尚未导出；保留目录，不重跑')
    # Original ZIP is preserved, not unpacked or rewritten; it already contains
    # the candidate assessment and its input digest map.
    with archive.open('xb') as stream: stream.write(original_zip.read_bytes())
    write_new(ROOT/'heart-video5-export.json', dict(package_manifest_sha256=checked['package_manifest_sha256'],
        archive_sha256=sha(archive), original_archive_sha256=sha(original_zip), startup_budget=dict(budget)))
    print('请回传 heart-video5-results.zip；结束后无信号正常，失败不自动重试。', flush=True)
    from IPython.display import FileLink, display
    display(FileLink(str(archive.relative_to(Path.cwd()))))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle', action='store_true'); parser.parse_args()
    print(json.dumps(verify_package(ROOT), ensure_ascii=False))
