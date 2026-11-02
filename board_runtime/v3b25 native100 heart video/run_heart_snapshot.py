"""Manual heart-only candidate. CLI never starts hardware."""
import argparse
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode = True
from heart_snapshot_guard import verify_candidate, assess, sha, write_new

ROOT = Path(__file__).resolve().parent


def run_static60(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-HEART-SNAPSHOT25':
        raise ValueError('requires hardware=True and RUN-HEART-SNAPSHOT25 confirmation')
    checked = verify_candidate(ROOT)
    directory = ROOT/'frozen/live_results/joint-heart-static60'
    archive = ROOT/'heart-snapshot-results.zip'
    if (ROOT/'joint-heart-attempt.json').exists() or directory.exists() or archive.exists():
        raise FileExistsError('本目录已有尝试或结果，保留它们，不重复运行')
    import joint_heart_worker as original_worker
    import run_joint_heart as original_entry
    from heart_snapshot_worker import start_owner
    previous = original_worker.start_owner
    original = {}
    failure = None
    print('快照单次构造候选：只做心率，正式静止60秒；不启动视频。', flush=True)
    print('25/25、原算法/GC/700点预热及全部保护不变；失败不自动重试。', flush=True)
    original_worker.start_owner = start_owner
    try:
        original = original_entry.run_static60(hardware=True, confirmation='RUN-JOINT-HEART25')
    except BaseException as exc:
        failure = dict(type=type(exc).__name__, message=str(exc))
    finally:
        original_worker.start_owner = previous
    # Read/export only after the original coordinator has returned; never force
    # unknown hardware to stop, and never label incomplete cleanup as success.
    post_errors = []
    owner = {}
    try:
        path = directory/'owner_heart_snapshot.json'
        if path.is_file():
            owner = json.loads(path.read_text(encoding='utf-8'))
    except BaseException as exc:
        post_errors.append(dict(stage='owner_report', type=type(exc).__name__, message=str(exc)))
    unchanged = False
    try:
        after = verify_candidate(ROOT)
        unchanged = after['candidate_manifest_sha256'] == checked['candidate_manifest_sha256']
        if not unchanged:
            raise ValueError('candidate manifest changed during run')
    except BaseException as exc:
        post_errors.append(dict(stage='post_identity', type=type(exc).__name__, message=str(exc)))
    result = assess(original, owner, inputs_unchanged=unchanged,
                    wrapper_error=failure, post_errors=post_errors)
    result.update(candidate_manifest_sha256=checked['candidate_manifest_sha256'],
                  base_manifest_sha256=checked['package_manifest_sha256'],
                  original_report='joint_heart_result.json', owner_report='owner_heart_snapshot.json')
    directory.mkdir(parents=True, exist_ok=True)
    result['input_sha256'] = {p.relative_to(directory).as_posix(): sha(p)
                             for p in sorted(directory.rglob('*')) if p.is_file() and p.suffix != '.zip'}
    write_new(directory/'heart_snapshot_result.json', result)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as package:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.suffix != '.zip':
                package.write(path, arcname=path.relative_to(directory).as_posix())
    print('快照候选静止基础小试完整：'+str(result['heart_snapshot_static_pilot_completed']), flush=True)
    print('未通过项：'+str([key for key, value in result['checks'].items() if not value]), flush=True)
    print(result['scope_cn'], flush=True)
    print('请保留并回传 heart-snapshot-results.zip；不要自动重试。', flush=True)
    from IPython.display import FileLink, display
    display(FileLink(str(archive.relative_to(Path.cwd()))))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-bundle', action='store_true')
    parser.parse_args()
    print(json.dumps(verify_candidate(ROOT), ensure_ascii=False))
