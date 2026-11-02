"""Restore byte-preserved runtime/Skills into a NEW external directory, offline.

One-time preparation only: no application import, PL, native ARM library, sensor
or video access. Published names stay lower-case ASCII; deployed names preserve
the frozen application and Skills loader contracts.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


def digest(data):
    return hashlib.sha256(data).hexdigest()


def relative(name, *, published=False):
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError("invalid mapped path")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
        raise ValueError("non-canonical mapped path: " + name)
    if published and any(not re.fullmatch(r"[a-z0-9_.-]+", p) for p in path.parts):
        raise ValueError("noncompliant published path: " + name)
    if any(p.endswith((".", " ")) for p in path.parts):
        raise ValueError("ambiguous mapped path: " + name)
    return path


def validated_records(root, group):
    root = Path(root).resolve(strict=True)
    doc = json.loads((root / "deployment_map.json").read_text(encoding="utf-8"))
    if doc.get("schema") != "verified_deployment_map_v1" or group not in ("runtime", "skills"):
        raise ValueError("unknown deployment map or group")
    rows, sources, destinations = [], set(), set()
    for row in doc["files"]:
        prefix = {"runtime": "board_runtime/", "skills": "skill/skills/"}.get(row["group"])
        source = relative(row["published"], published=True)
        target = relative(row["deployed"])
        if prefix is None or not str(source).startswith(prefix) or not str(target).startswith(prefix):
            raise ValueError("mapped group prefix differs")
        for seen, value in ((sources, str(source)), (destinations, str(target))):
            folded = value.casefold()
            if folded in seen:
                raise ValueError("duplicate or case-colliding mapping: " + value)
            seen.add(folded)
        if not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) or type(row["bytes"]) is not int or row["bytes"] < 0:
            raise ValueError("invalid mapped identity")
        if row["group"] == group:
            path = root.joinpath(*source.parts)
            if any(root.joinpath(*source.parts[:i]).is_symlink() for i in range(1, len(source.parts) + 1)):
                raise ValueError("symlink in source mapping")
            if not path.resolve(strict=True).is_relative_to(root):
                raise ValueError("mapped source escaped checkout")
            data = path.read_bytes()
            if len(data) != row["bytes"] or digest(data) != row["sha256"]:
                raise ValueError("mapped source identity differs: " + str(source))
            rows.append(row)
    if not rows:
        raise ValueError("empty deployment group")
    leaves = {row["deployed"].casefold() for row in rows}
    for row in rows:
        if any(str(p).casefold() in leaves for p in PurePosixPath(row["deployed"]).parents if str(p) != "."):
            raise ValueError("file/directory mapping collision")
    return rows


def prepare(root, group, output):
    root = Path(root).resolve(strict=True)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError("preserve existing directory; choose a NEW output directory")
    output = output.resolve()
    if output.is_relative_to(root):
        raise ValueError("output must be outside the published checkout")
    rows = validated_records(root, group)
    output.mkdir(parents=True, exist_ok=False)
    for row in rows:
        source = root / row["published"]
        target = output.joinpath(*relative(row["deployed"]).parts)
        if not target.resolve().is_relative_to(output):
            raise ValueError("mapped destination escaped output")
        data = source.read_bytes()
        if len(data) != row["bytes"] or digest(data) != row["sha256"]:
            raise ValueError("source changed during preparation")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        if digest(target.read_bytes()) != row["sha256"]:
            raise ValueError("destination verification failed")
    result = {"prepared": True, "group": group, "files_verified": len(rows),
              "output": str(output), "application_executed": False, "hardware_accessed": False,
              "hot_path_changes": False, "algorithm_changes": False,
              "deployed_names_restored": True}
    if group == "runtime":
        result["notebook"] = str(output / "board_runtime/runtime/ContinuousDemo25.ipynb")
        result["next_check"] = "python -B " + str(output / "board_runtime/verify_portable.py")
    else:
        result["skill_root"] = str(output / "skill/skills")
    (output / "preparation_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group", choices=("runtime", "skills"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.check_only and args.output is not None:
        parser.error("--check-only does not accept --output")
    if not args.check_only and args.output is None:
        parser.error("--output is required for preparation")
    root = Path(__file__).resolve().parent
    from verify_public_source import verify
    verified = verify(root)
    if not verified["static_file_identity_passed"]:
        print(json.dumps(verified, ensure_ascii=False, indent=2))
        return 2
    if args.check_only:
        result = {"mapped_inputs_verified": True, "files": len(validated_records(root, args.group)),
                  "hardware_accessed": False, "output_created": False}
    else:
        result = prepare(root, args.group, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
