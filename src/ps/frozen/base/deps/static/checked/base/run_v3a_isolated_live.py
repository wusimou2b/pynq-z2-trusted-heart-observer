"""V3-A PS进程隔离小试：默认只检查；硬件仅限一次60秒静止，无绘图。"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import uuid


def main(argv=None):
    from heart_v3a.live import board
    from heart_v3a.live.contracts import LiveSettings
    from heart_v3a.live.isolated import IsolatedLiveSession
    parser = argparse.ArgumentParser(description='PS独立进程／主进程唯一硬件所有者，固定60秒静止小试')
    parser.add_argument('bundle', nargs='?', type=Path, default=Path(__file__).resolve().parent)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--check-bundle', action='store_true')
    action.add_argument('--hardware', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not args.hardware:
        identity = board._validated_bundle(args.bundle)
        print(json.dumps(dict(bundle_validated=True, base_manifest_sha256=identity['base_manifest_sha256'],
            entry='isolated_live_pilot', hardware_loaded=False, board_tested=False,
            live_50hz_passed=False, auto_beta_effect_passed=False, board_ddr_verified=False,
            v3a_complete=False), ensure_ascii=False))
        return 0
    output = args.output or args.bundle / 'live_results' / (
        'isolated-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    session = None
    interrupted = False
    print('隔离小试：请放稳手指。只运行本单元，不同时采集或绘图。', flush=True)
    print('将加载原Overlay；DDR仍未验收。独立PS进程预热另计，最长60秒。', flush=True)
    try:
        session = board.prepare_live_session(args.bundle, output, LiveSettings(), hardware=True,
            session_factory=IsolatedLiveSession)
        session.start()
        print('预热完成，已进入60秒正式静止采集；不显示波形。', flush=True)
        while session.snapshot().state == 'running':
            time.sleep(.1)
    except KeyboardInterrupt:
        interrupted = True
        print('用户中断：请求原有界停止，不自动重试。', flush=True)
    finally:
        summary = session.stop() if session is not None else None
        if summary is not None:
            print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
            print('结果目录：', output.resolve(), flush=True)
            if not summary['cleanup_complete']:
                print('清理尚未完成：不要运行其他硬件入口，保留本输出。', flush=True)
    if summary is None:
        print('预检未完成，尚无正式采集记录。', flush=True)
        return 130 if interrupted else 1
    return 130 if interrupted else (0 if summary['cleanup_complete'] and summary['fault'] is None else 1)


if __name__ == '__main__':
    raise SystemExit(main())
