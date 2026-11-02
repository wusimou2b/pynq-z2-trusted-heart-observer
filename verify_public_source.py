"""Read-only public-source file identity check, without project imports."""
import hashlib
import json
from pathlib import Path, PurePosixPath

root=Path(__file__).resolve().parent
manifest=json.loads((root/"public_export_manifest.json").read_text(encoding="utf-8"))
records={r["path"]:r for r in manifest["files"]}
actual={p.relative_to(root).as_posix() for p in root.rglob("*")
        if p.is_file() and p.relative_to(root).parts[0] != ".git"}
errors=[]
if actual!=set(records)|{"public_export_manifest.json"}:
    errors.append({"missing":sorted(set(records)-actual),"extra":sorted(actual-set(records)-{"public_export_manifest.json"})})
for name,r in records.items():
    rel=PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts or "\\" in name or ":" in name:
        errors.append({"unsafe_path":name});continue
    p=root.joinpath(*rel.parts)
    if p.is_file():
        data=p.read_bytes()
        if len(data)!=r["bytes"] or hashlib.sha256(data).hexdigest()!=r["sha256"]:errors.append({"identity_mismatch":name})
print(json.dumps({"static_file_identity_passed":not errors,"files":len(records),"project_executed":False,"clean_build_verified":False,"board_accessed":False,"errors":errors},ensure_ascii=False,indent=2))
raise SystemExit(0 if not errors else 2)
