#!/usr/bin/env python3
"""User-run metadata collector. Standard library only; never imports project packages.

This draft was not executed during the delivery audit. Run with the same Python
interpreter used by the successful Notebook environment. It reads package and OS
metadata and writes one new JSON file only when explicitly requested.
"""
import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import sys
import sysconfig
from datetime import datetime, timezone

PACKAGES = (
    "pynq", "numpy", "scipy", "opencv-python", "opencv-contrib-python",
    "opencv-python-headless", "ipython", "jupyter", "notebook", "jupyter-server",
    "ipykernel", "jupyter-client", "jupyter-core", "nbformat", "ipywidgets",
    "bokeh", "matplotlib", "plotly", "tornado", "pyzmq", "traitlets",
)
DPKG_PACKAGES = {
    "pynq", "python3-pynq", "python3-numpy", "python3-scipy", "python3-opencv",
    "python3-ipython", "ipython3", "jupyter", "jupyter-core", "jupyter-notebook",
    "python3-notebook", "python3-ipykernel", "python3-jupyter-client",
    "python3-jupyter-core", "python3-ipywidgets", "python3-matplotlib",
    "python3-bokeh", "python3-tornado", "gcc-11", "libc6", "python3.10",
}


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def distribution_metadata(name):
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {"status": "metadata_not_found", "version": None}
    raw = dist.read_text("METADATA")
    if raw is None:
        raw = dist.read_text("PKG-INFO")
    return {
        "status": "metadata_found_without_importing_package",
        "name": dist.metadata.get("Name", name),
        "version": dist.version,
        "metadata_sha256": digest(raw.encode("utf-8")) if raw is not None else None,
    }


def plain_file(path):
    p = Path(path)
    try:
        blob = p.read_bytes()
    except OSError as exc:
        return {"status": "unavailable", "error_type": type(exc).__name__}
    return {"status": "read", "sha256": digest(blob), "text": blob.decode("utf-8", errors="replace")}


def operating_system_metadata():
    result = {}
    if hasattr(os, "uname"):
        u = os.uname()
        result["uname"] = {"system": u.sysname, "release": u.release,
                           "version": u.version, "machine": u.machine}
    release = plain_file("/etc/os-release")
    if release["status"] == "read":
        fields = {}
        for line in release.pop("text").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if key in {"NAME", "ID", "ID_LIKE", "VERSION", "VERSION_ID", "PRETTY_NAME", "BUILD_ID"}:
                    fields[key] = value.strip().strip('"')
        release["fields"] = fields
    result["os_release"] = release
    # Plain package database only; no package manager, compiler, service or device is invoked.
    db = plain_file("/var/lib/dpkg/status")
    if db["status"] == "read":
        packages = {}
        for stanza in db.pop("text").split("\n\n"):
            values = {}
            for line in stanza.splitlines():
                if line and not line[0].isspace() and ": " in line:
                    key, value = line.split(": ", 1)
                    if key in {"Package", "Status", "Version", "Architecture"}:
                        values[key] = value
            if values.get("Package") in DPKG_PACKAGES:
                packages[values["Package"]] = {k: values.get(k) for k in ("Status", "Version", "Architecture")}
        db["selected_packages"] = packages
    result["dpkg_status"] = db
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="new JSON path; existing files are refused")
    parser.add_argument("--context", default="operator did not specify test/environment association")
    args = parser.parse_args()
    result = {
        "schema": "trusted_heart_readonly_environment_metadata_v1",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "operator_context": args.context,
        "scope": "metadata only; no project imports, package imports, subprocesses, network or devices",
        "python": {"version": sys.version, "implementation": sys.implementation.name,
                   "byteorder": sys.byteorder, "platform": sys.platform,
                   "soabi": sysconfig.get_config_var("SOABI"),
                   "executable_basename": Path(sys.executable).name},
        "distributions": {name: distribution_metadata(name) for name in PACKAGES},
        "os": operating_system_metadata(),
        "sd_image_original_filename": None,
        "sd_image_original_sha256": None,
        "client_browser_product_and_version": None,
        "limitations": [
            "Metadata collection does not prove this is the environment of a historical test.",
            "Missing Python distribution metadata does not prove an apt-provided module is absent.",
            "Image filename/hash and client-browser version require separate operator evidence.",
        ],
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
