"""Rebuild preserved physical inputs in a fresh directory; no board access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
from zipfile import ZipFile


HERE = Path(__file__).resolve().parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_inputs() -> tuple[dict, dict[str, bytes]]:
    index = json.loads((HERE / "inputs" / "physical-inputs.json").read_bytes())
    archive = HERE / "inputs" / "physical-inputs.zip"
    if digest(archive.read_bytes()) != index["archive_sha256"]:
        raise ValueError("physical input archive hash mismatch")
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)) or set(names) != set(index["members"]):
            raise ValueError("physical input member set mismatch")
        payload = {}
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                raise ValueError("unsafe input member: " + name)
            data = zipped.read(name)
            expected = index["members"][name]
            if digest(data) != expected["sha256"] or len(data) != expected["bytes"]:
                raise ValueError("input member hash mismatch: " + name)
            payload[name] = data
    for name, expected in index["scripts"].items():
        if digest((HERE / "scripts" / name).read_bytes()) != expected:
            raise ValueError("preserved build script hash mismatch: " + name)
    return index, payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="fresh build directory, outside this delivery")
    parser.add_argument("--vivado", default="vivado", help="Vivado 2024.1 launcher")
    parser.add_argument("--execute", action="store_true", help="actually run synthesis, route and bit generation")
    parser.add_argument("--check-only", action="store_true", help="verify archived inputs without launching tools")
    args = parser.parse_args()
    if args.execute and args.check_only:
        parser.error("--execute and --check-only are mutually exclusive")
    index, payload = checked_inputs()
    if args.check_only:
        print(json.dumps({"input_hashes_verified": True, "members": len(payload),
                          "vivado_executed": False, "known_missing_documentation": index["known_missing_documentation"]}, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required unless --check-only is used")
    session = args.output.resolve()
    delivery = HERE.parent
    if session == delivery or session.is_relative_to(delivery):
        parser.error("output must be outside the delivery tree")
    if session.exists():
        parser.error("output already exists; preserve previous attempts and choose a fresh directory")
    scripts = HERE / "scripts"
    stages = [
        ("prepare", "prepare-main-spatial.tcl", [str(session)]),
        ("route", "main-joint-route.tcl", [str(session)]),
        ("bitstream", "write-joint-bitstream.tcl", [str(session / "routed.dcp"), str(session)]),
    ]
    commands = [
        [args.vivado, "-mode", "batch", "-notrace", "-source", str(scripts / script),
         "-log", str(session / (stage + ".log")), "-journal", str(session / (stage + ".jou")), "-tclargs", *arguments]
        for stage, script, arguments in stages
    ]
    if not args.execute:
        print(json.dumps({"input_hashes_verified": True, "vivado_executed": False,
                          "commands": commands, "next_step": "add --execute to run the build"}, indent=2))
        return 0
    launcher = shutil.which(args.vivado)
    if launcher is None:
        raise FileNotFoundError("Vivado launcher was not found: " + args.vivado)
    launcher = str(Path(launcher).resolve())
    version = subprocess.run([launcher, "-version"], capture_output=True, text=True, check=True)
    if "v2024.1" not in version.stdout + version.stderr:
        raise RuntimeError("preserved project requires Vivado 2024.1; different versions need separate qualification")
    session.mkdir(parents=True, exist_ok=False)
    for name, data in payload.items():
        target = session.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (session / "artifacts").mkdir()
    result = {"input_archive_sha256": index["archive_sha256"], "vivado_version": version.stdout,
              "steps": [], "hardware_accessed": False, "clean_build_completed": False,
              "complete_system_acceptance": False, "error": None}
    try:
        for (stage, _, _), command in zip(stages, commands):
            command[0] = launcher
            with (session / (stage + "-console.log")).open("w", encoding="utf-8") as log:
                completed = subprocess.run(command, cwd=session, stdout=log, stderr=subprocess.STDOUT)
            result["steps"].append({"stage": stage, "command": command, "returncode": completed.returncode})
            if completed.returncode:
                raise RuntimeError(stage + " failed; retain this directory and inspect its logs")
        bitstream = session / "artifacts" / "heart_v3b25.bit"
        handoff = session / "artifacts" / "heart_v3b25.hwh"
        if not bitstream.is_file() or not (session / "generated.hwh").is_file():
            raise RuntimeError("bitstream or matching generated HWH is absent")
        shutil.copyfile(session / "generated.hwh", handoff)
        result["artifacts"] = {str(path.relative_to(session)): digest(path.read_bytes())
                               for path in (bitstream, handoff)}
        result["clean_build_completed"] = True
    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        (session / "build-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
