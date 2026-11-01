"""Manual complete-read joint trial. CLI only validates files without hardware."""
import argparse
import json
from pathlib import Path
import sys
import zipfile
sys.dont_write_bytecode = True

if __package__:
    from .iic_handoff_guard import verify_package, assess_joint, sha, write_new
    from .iic_handoff_build import verify_build
    from .joint_startup import replace_attribute
    from .joint_owner import require_board
    from .yuyv_joint_guard import install_assessment
else:
    from iic_handoff_guard import verify_package, assess_joint, sha, write_new
    from iic_handoff_build import verify_build
    from joint_startup import replace_attribute
    from joint_owner import require_board
    from yuyv_joint_guard import install_assessment

ROOT = Path(__file__).resolve().parent


def run_joint60(*, hardware=False, confirmation=None):
    if hardware is not True or confirmation != 'RUN-IIC-HANDOFF60':
        raise ValueError('requires hardware=True and RUN-IIC-HANDOFF60')
    require_board(); root = ROOT
    directory = root / 'frozen/live_results/joint-concurrent5-static60'
    attempt, archive = root / 'iic-handoff-attempt.json', root / 'iic-handoff-results.zip'
    if any(p.exists() for p in (directory, attempt, archive, root / 'snapshot5-attempt.json', root / 'yuyv-joint-attempt.json')) or any(root.glob('joint-*-attempt.json')):
        raise FileExistsError('existing attempt/results; preserve, no retry/overwrite')
    checked, build = verify_package(root), verify_build(root)
    if __package__:
        from . import run_joint_snapshot as inherited, joint_snapshot_worker as original
        from .iic_handoff_worker import start_owner
    else:
        import run_joint_snapshot as inherited, joint_snapshot_worker as original
        from iic_handoff_worker import start_owner
    pair = json.loads((root / 'yuyv-artifacts.json').read_text('utf-8'))['files']
    write_new(attempt, dict(schema='v3b25_iic_handoff_attempt_v1', automatic_retry=False,
        manifest_sha256=checked['iic_handoff_manifest_sha256'], library_sha256=build['library_sha256'], pair_sha256=pair))
    print('IIC完整读取候选：相机/HDMI OUT接好、手指放稳，其他板端任务安全结束；只运行一次。', flush=True)
    print('25/25Hz心率＋5fps视频共同60秒；启动/原700点预热另计。原50ms/配对/GC/保护/PS退出策略不变。', flush=True)
    print('只变更IIC交接；加载已验证YUYV电路一次。原继承报告仅描述其原层，当前实现以iic_handoff_joint60.json为准。', flush=True)
    old = {}; failure = None
    try:
        with replace_attribute(original, 'start_owner', start_owner), install_assessment(pair):
            old = inherited.run_snapshot60(hardware=True, confirmation='RUN-JOINT-SNAPSHOT5')
    except BaseException as exc: failure = dict(stage='inherited_snapshot', type=type(exc).__name__, message=str(exc))
    directory.mkdir(parents=True, exist_ok=True)
    owner = {}; errors = []
    try: owner = json.loads((directory / 'yuyv_iic_owner.json').read_text('utf-8'))
    except Exception as exc: errors.append(dict(stage='owner_report', type=type(exc).__name__, message=str(exc)))
    unchanged = False
    try:
        after, after_build = verify_package(root), verify_build(root)
        unchanged = bool(after['iic_handoff_manifest_sha256'] == checked['iic_handoff_manifest_sha256'] and after_build == build)
    except BaseException as exc: errors.append(dict(stage='postrun_identity', type=type(exc).__name__, message=str(exc)))
    result = assess_joint(old, owner, build=build, inputs_unchanged=unchanged,
        wrapper_error=failure or (dict(stage='report_or_identity', details=errors) if errors else None))
    result.update(inputs_unchanged=unchanged, report_errors=errors, native_build=build,
        iic_handoff_manifest_sha256=checked['iic_handoff_manifest_sha256'], pair_sha256=pair,
        inherited_report='snapshot_probe.json', native_owner_report='yuyv_iic_owner.json',
        input_sha256={p.relative_to(directory).as_posix():sha(p) for p in sorted(directory.rglob('*')) if p.is_file() and p.suffix != '.zip'})
    write_new(directory / 'iic_handoff_joint60.json', result)
    with (directory / 'iic_handoff_joint60.txt').open('x', encoding='utf-8') as stream:
        stream.write('IIC完整读取联合小试完整：' + str(result['iic_handoff_joint60_completed']) + '\n' + result['scope_cn'] + '\n')
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and path.suffix != '.zip': z.write(path, path.relative_to(directory).as_posix())
        for name in ('iic-handoff-attempt.json', 'handoff-build.json', 'handoff-build-attempt.json',
                     'iic-handoff-manifest.json', 'yuyv-artifacts.json'):
            if (root / name).is_file(): z.write(root / name, 'entry/' + name)
    print('IIC完整读取联合小试完整：', result['iic_handoff_joint60_completed'], '；不是完整验收。', flush=True)
    print('未通过项：', [k for k, v in result['checks'].items() if not v], flush=True)
    from IPython.display import display, FileLink
    display(FileLink(str(archive.relative_to(Path.cwd()))))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--check-bundle', action='store_true', required=True)
    parser.parse_args(); print(json.dumps(verify_package(ROOT), ensure_ascii=False))
