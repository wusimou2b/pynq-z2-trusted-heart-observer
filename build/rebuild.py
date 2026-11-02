"""Check, assemble and build source inputs in a fresh directory; no board access.

The public archive contains project sources, not redistributable copies of the
tool-generated HLS RTL. Pinned upstream inputs are fetched and HLS RTL is generated
locally with the user's licensed 2024.1 tools before the original Vivado stages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_relative(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (not name or path.is_absolute() or any(p in ("..", ".") for p in path.parts)
            or "\\" in name or ":" in name or str(path) != name):
        raise ValueError("unsafe input member: " + name)
    return path


def checked_inputs(build: Path = HERE) -> tuple[dict, dict[str, bytes]]:
    index = json.loads((build / "inputs" / "physical-inputs.json").read_bytes())
    if index["schema"] != "physical_inputs_source_v2":
        raise ValueError("unsupported physical-input contract")
    archive = build / "inputs" / "physical-inputs.zip"
    if digest(archive.read_bytes()) != index["archive_sha256"]:
        raise ValueError("physical input archive hash mismatch")
    with ZipFile(archive) as zipped:
        names = zipped.namelist()
        if len(names) != len(set(names)) or set(names) != set(index["members"]):
            raise ValueError("physical input member set mismatch")
        payload = {}
        for name in names:
            safe_relative(name)
            if not re.fullmatch(r"[a-z0-9_.\-/]+", name):
                raise ValueError("noncompliant public archive name: " + name)
            data = zipped.read(name)
            expected = index["members"][name]
            if digest(data) != expected["sha256"] or len(data) != expected["bytes"]:
                raise ValueError("input member hash mismatch: " + name)
            payload[name] = data
    destinations = set(payload)
    for row in index["external_files"]:
        safe_relative(row["path"])
        if row["path"] in destinations:
            raise ValueError("external file would overwrite input: " + row["path"])
        destinations.add(row["path"])
        if not re.fullmatch(r"https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/.+", row["url"]):
            raise ValueError("external source is not pinned to a Git commit")
    for name, expected in index["scripts"].items():
        safe_relative(name)
        if digest((build / "scripts" / name).read_bytes()) != expected:
            raise ValueError("preserved build script hash mismatch: " + name)
    return index, payload


def read_external(row: dict, cache: Path | None = None) -> bytes:
    if cache is not None:
        data = cache.joinpath(*safe_relative(row["path"]).parts).read_bytes()
    else:
        request = urllib.request.Request(row["url"], headers={"User-Agent": "trusted-heart-source-rebuild/2"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    if digest(data) != row["sha256"] or len(data) != row["bytes"]:
        raise ValueError("external input hash mismatch: " + row["path"])
    return data


def stage_inputs(session: Path, payload: dict[str, bytes], index: dict,
                 cache: Path | None = None) -> list[dict]:
    for name, data in payload.items():
        target = session.joinpath(*safe_relative(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    receipts = []
    for row in index["external_files"]:
        data = read_external(row, cache)
        target = session.joinpath(*safe_relative(row["path"]).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        receipts.append({"path": row["path"], "sha256": digest(data), "url": row["url"]})
    return receipts


def install_hls_archive(archive: Path, destination: Path, expected_core: str) -> dict:
    if destination.exists():
        raise FileExistsError("generated HLS destination already exists")
    with ZipFile(archive) as zipped:
        files = [x for x in zipped.infolist() if not x.is_dir()]
        names = [x.filename for x in files]
        if len(names) != len(set(names)):
            raise ValueError("duplicate HLS archive member")
        for entry in files:
            safe_relative(entry.filename)
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("HLS archive contains a symlink")
        if "component.xml" not in names:
            raise ValueError("HLS export lacks component.xml")
        component = ET.fromstring(zipped.read("component.xml"))
        ns = {"s": "http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009"}
        vlnv = ":".join(component.findtext("s:" + item, namespaces=ns) or "" for item in ("vendor", "library", "name", "version"))
        if vlnv != "xilinx.com:hls:" + expected_core + ":1.0":
            raise ValueError("unexpected generated HLS identity: " + vlnv)
        for entry in files:
            target = destination.joinpath(*safe_relative(entry.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zipped.read(entry))
    return {"core": expected_core, "vlnv": vlnv, "archive_sha256": digest(archive.read_bytes()), "members": len(files)}


def tool(command: str) -> tuple[str, str]:
    launcher = shutil.which(command)
    if launcher is None:
        raise FileNotFoundError("tool launcher was not found: " + command)
    launcher = str(Path(launcher).resolve())
    version = subprocess.run([launcher, "-version"], capture_output=True, text=True, env=tool_environment())
    output = version.stdout + version.stderr
    # Vivado's Windows launcher can return 1 after a successful version print.
    # This exception applies only to -version, never to build-stage exit codes.
    if not re.search(r"(?:vivado|Vitis HLS).*v2024\.1\b", output, re.IGNORECASE):
        raise RuntimeError("source inputs require 2024.1; different tools need separate qualification")
    return launcher, output


def tool_environment() -> dict[str, str]:
    environment = os.environ.copy()
    # Some process hosts omit this standard Windows variable. Vendor loaders
    # otherwise silently exit before invoking their executables.
    if os.name == "nt" and "PROCESSOR_ARCHITECTURE" not in environment:
        machine = platform.machine().upper()
        if machine not in ("AMD64", "ARM64", "X86"):
            raise RuntimeError("cannot identify native Windows architecture")
        environment["PROCESSOR_ARCHITECTURE"] = machine
    return environment


def vivado_stages(session: Path, execute: bool) -> list[tuple[str, str, list[str]]]:
    stages = [("prepare", "prepare-main-spatial.tcl", [str(session)])]
    if execute:
        # Keep base-route evidence intact. The historical final implementation
        # used a separate physical optimization pass, followed by the same
        # strict bitstream timing/DRC gate.
        postroute = session / "postroute"
        stages.extend([
            ("route", "main-joint-route.tcl", [str(session)]),
            ("postroute", "physical-postroute.tcl", [str(postroute), str(session / "routed.dcp")]),
            ("bitstream", "write-joint-bitstream.tcl", [str(postroute / "routed.dcp"), str(session)]),
        ])
    return stages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="fresh build directory outside the delivery")
    parser.add_argument("--vivado", default="vivado", help="Vivado 2024.1 launcher")
    parser.add_argument("--hls", default="vitis_hls", help="Vitis HLS 2024.1 launcher")
    parser.add_argument("--external-cache", type=Path, help="optional offline cache preserving pinned relative paths")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true", help="fetch, generate HLS, synthesize, route and write bit/HWH")
    mode.add_argument("--prepare-only", action="store_true", help="fetch, generate HLS and validate/generate the Vivado project only")
    mode.add_argument("--check-only", action="store_true", help="verify bundled inputs without fetching or launching tools")
    args = parser.parse_args(argv)
    index, payload = checked_inputs()
    if args.check_only:
        print(json.dumps({"input_hashes_verified": True, "bundled_members": len(payload),
                          "pinned_external_files": len(index["external_files"]), "vivado_executed": False,
                          "external_files_downloaded": False, "hls_generated": False,
                          "clean_build_completed": False, "hardware_accessed": False}, indent=2))
        return 0
    if args.output is None:
        parser.error("--output is required unless --check-only is used")
    session = args.output.resolve()
    delivery = HERE.parent
    if session == delivery or session.is_relative_to(delivery):
        parser.error("output must be outside the delivery tree")
    if session.exists():
        parser.error("output already exists; preserve it and choose a fresh directory")
    if not args.execute and not args.prepare_only:
        print(json.dumps({"input_hashes_verified": True, "output": str(session),
                          "steps": ["verify tool versions", "restore project sources", "fetch pinned external files",
                                    "generate color_convert and pixel_unpack from C++", "prepare", "route", "postroute", "bitstream"],
                          "vivado_executed": False, "next_step": "add --execute to perform the build"}, indent=2))
        return 0
    session.mkdir(parents=True, exist_ok=False)
    result = {"input_archive_sha256": index["archive_sha256"], "steps": [], "external_files": [],
              "hls_exports": [], "hardware_accessed": False, "clean_build_completed": False,
              "complete_system_acceptance": False, "runtime_assets_replaced": False, "error": None}
    try:
        vivado, result["vivado_version"] = tool(args.vivado)
        hls, result["hls_version"] = tool(args.hls)
        result["external_files"] = stage_inputs(session, payload, index, args.external_cache)
        (session / "artifacts").mkdir()
        (session / "hls_work").mkdir()
        if args.execute:
            (session / "postroute" / "reports").mkdir(parents=True)
        def run(stage: str, command: list[str], extra_environment: dict[str, str] | None = None) -> None:
            print("BUILD_STAGE " + stage, flush=True)
            environment = tool_environment()
            environment.update(extra_environment or {})
            with (session / (stage + "-console.log")).open("w", encoding="utf-8") as log:
                completed = subprocess.run(command, cwd=session, stdout=log, stderr=subprocess.STDOUT, env=environment)
            result["steps"].append({"stage": stage, "command": command, "environment": extra_environment or {}, "returncode": completed.returncode})
            (session / "build-progress.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            if completed.returncode:
                raise RuntimeError(stage + " failed; retain this directory and inspect its logs")
        for core in index["hls_cores"]:
            run("hls_" + core, [hls, "-f", str(HERE / "scripts" / "generate-hls.tcl")],
                {"THO_BUILD_SESSION": str(session), "THO_HLS_CORE": core})
            result["hls_exports"].append(install_hls_archive(session / "hls_work" / (core + "_ip.zip"), session / "ip_repo" / core, core))
        stages = vivado_stages(session, args.execute)
        for stage, script, arguments in stages:
            run(stage, [vivado, "-mode", "batch", "-notrace", "-source", str(HERE / "scripts" / script),
                        "-log", str(session / (stage + ".log")), "-journal", str(session / (stage + ".jou")), "-tclargs", *arguments])
        result["project_prepared"] = True
        if args.execute:
            bitstream = session / "artifacts" / "heart_v3b25.bit"
            handoff = session / "artifacts" / "heart_v3b25.hwh"
            if not bitstream.is_file() or not (session / "generated.hwh").is_file():
                raise RuntimeError("generated bitstream or matching HWH is absent")
            shutil.copyfile(session / "generated.hwh", handoff)
            result["artifacts"] = {str(path.relative_to(session)): digest(path.read_bytes()) for path in (bitstream, handoff)}
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
