"""Verify published names and exact file bytes; never import board runtime."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

def verify(root):
    root = Path(root).resolve(strict=True)
    manifest = json.loads((root / "public_export_manifest.json").read_text(encoding="utf-8"))
    rows = manifest["files"]
    records = {row["path"]: row for row in rows}
    errors = []
    if len(records) != len(rows):
        errors.append({"duplicate_manifest_paths": True})
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*")
              if p.is_file() and p.relative_to(root).parts[0] != ".git"}
    expected = set(records) | {"public_export_manifest.json"}
    if actual != expected:
        errors.append({"missing": sorted(expected - actual), "extra": sorted(actual - expected)})
    for name in sorted(actual):
        if any(not re.fullmatch(r"[a-z0-9_.-]+", part) for part in PurePosixPath(name).parts):
            errors.append({"noncompliant_name": name})
    for name, row in records.items():
        rel = PurePosixPath(name)
        if (not name or rel.is_absolute() or ".." in rel.parts or "\\" in name
                or ":" in name or rel.as_posix() != name):
            errors.append({"unsafe_path": name})
            continue
        path = root.joinpath(*rel.parts)
        if path.is_symlink() or (path.exists() and not path.resolve().is_relative_to(root)):
            errors.append({"escaped_path": name})
            continue
        if path.is_file():
            data = path.read_bytes()
            if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                errors.append({"identity_mismatch": name})
    return {"static_file_identity_passed": not errors, "files": len(records),
            "project_executed": False, "board_accessed": False,
            "scope": "Published names and file identities only; not build or board acceptance.",
            "errors": errors}


if __name__ == "__main__":
    result = verify(Path(__file__).resolve().parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["static_file_identity_passed"] else 2)
