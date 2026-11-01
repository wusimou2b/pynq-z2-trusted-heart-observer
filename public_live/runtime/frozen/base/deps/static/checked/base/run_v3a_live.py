"""默认身份检查；显式--hardware才加载实时Overlay。"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import time
import uuid
from heart_v3a.live import board
from heart_v3a.live.contracts import LiveSettings


def main(argv=None):
    parser = argparse.ArgumentParser(description="V3-A实时50 Hz检查／显式采集，不开放算法调参")
    parser.add_argument("bundle", nargs="?", type=Path, default=Path(__file__).resolve().parent)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check-bundle", action="store_true")
    mode.add_argument("--hardware", action="store_true")
    parser.add_argument("--mode", choices=("baseline", "acceptance"), default="baseline")
    parser.add_argument("--protocol", choices=("static", "motion", "contact"), default="static")
    parser.add_argument("--duration", type=float, default=60.)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limits", type=Path)
    args = parser.parse_args(argv)
    settings = LiveSettings(args.mode, args.protocol, args.duration)
    if not args.hardware:
        identity = board._validated_bundle(args.bundle)
        print(json.dumps(dict(bundle_validated=True, base_manifest_sha256=identity["base_manifest_sha256"],
            board_tested=False, live_50hz_passed=False, board_ddr_verified=False), ensure_ascii=False))
        return 0
    output = args.output or args.bundle / "live_results" / ("live-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
    print("显式加载新Overlay；DDR遗留告警仍未验收。CLI无显示测量，首个完整基准请用新Notebook。")
    session = None
    try:
        session = board.prepare_live_session(args.bundle, output, settings, hardware=True, limits_path=args.limits)
        session.start()
        while session.snapshot().state == "running":
            time.sleep(.1)
    except KeyboardInterrupt:
        print("用户中断；请求有界停止。")
    finally:
        summary = session.stop() if session is not None else None
    if summary is None:
        print("预检中断，尚未建立采集记录；未宣称采集／清理验收通过。")
        return 130
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("结果目录：", output.resolve())
    return 0 if summary["cleanup_complete"] and summary["fault"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
