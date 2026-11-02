"""Stdlib-only package/after-run checks. Editable Notebook outputs are not code."""
import hashlib
import json
from pathlib import Path

if __package__:
    from .joint_owner import PAIR_HASHES,verify_pair
else:
    from joint_owner import PAIR_HASHES,verify_pair

FROZEN_MANIFEST_SHA="00879aa1d75813cdbc1cb644706b369e465615cb340c6a739b67e5fd9fa3adf8"
TOP_FILES={"heart_v3b25.bit","heart_v3b25.hwh","joint-artifacts.json","joint_owner.py",
           "joint_heart_binding.py","joint_heart_worker.py","joint_heart_guard.py",
           "run_joint_heart.py","README_HEART.md"}
FLAGS=dict.fromkeys(("live_25hz_passed","live_50hz_passed","auto_beta_effect_passed",
    "board_ddr_verified","limits_frozen","run_acceptance_passed","v3a_complete",
    "full_v3b_acceptance_passed"),False)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path,value):
    with Path(path).open("x",encoding="utf-8") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def notebook_code_hash(path):
    document=json.loads(Path(path).read_text(encoding="utf-8"))
    cells=["".join(c["source"]) for c in document["cells"] if c["cell_type"]=="code"]
    return hashlib.sha256(json.dumps(cells,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def verify_package(root):
    root=Path(root).resolve()
    path=root/"joint-heart-manifest.json"
    doc=json.loads(path.read_text(encoding="utf-8"))
    frozen=root/"frozen"
    original=frozen/"entry25-live-manifest.json"
    if sha(original)!=FROZEN_MANIFEST_SHA:
        raise ValueError("frozen heart manifest hash changed")
    reference=json.loads(original.read_text(encoding="utf-8"))
    expected=TOP_FILES|{"frozen/entry25-live-manifest.json"}|{"frozen/"+n for n in reference["files"]}
    if (doc.get("schema")!="v3b25_joint_heart_package_v1" or set(doc.get("files",{}))!=expected
            or (doc.get("raw_hz"),doc.get("processing_hz"),doc.get("adc_hz"),doc.get("fifo_sample_average"),doc.get("requested_duration_seconds"))!=(25,25,50,2,60)
            or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError("joint heart package scope/file map mismatch")
    for name,digest in doc["files"].items():
        target=root/name
        if target.is_symlink() or not target.is_file() or sha(target)!=digest:
            raise ValueError("joint heart package hash mismatch: "+name)
    for name,digest in reference["files"].items():
        if doc["files"].get("frozen/"+name)!=digest:
            raise ValueError("frozen reference file hash mismatch: "+name)
    if notebook_code_hash(root/"JointHeart25.ipynb")!=doc.get("notebook_code_sha256"):
        raise ValueError("joint heart executable Notebook cells changed")
    verify_pair(root)
    return dict(bundle_validated=True,frozen_files_verified=len(reference["files"]),
                package_manifest_sha256=sha(path),raw_hz=25,processing_hz=25,hardware_accessed=False,
                heart25_on_joint_passed=False,**FLAGS)


def changed_files(root,tracked):
    return [name for name,digest in tracked.items() if not (Path(root)/name).is_file() or sha(Path(root)/name)!=digest]


def assess_joint(original,joint,*,inputs_unchanged,wrapper_error=None):
    summary=original.get("summary") or {}
    preflight=summary.get("preflight") or {}
    cleanup=joint.get("cleanup") or {}
    checks=dict(inherited_static_pilot=original.get("candidate_static_pilot_completed") is True,
        joint_binding=joint.get("binding_installed") is True and joint.get("prepare_calls")==1 and preflight.get("joint_binding") is True,
        joint_bit_identity=preflight.get("bit_sha256")==PAIR_HASHES["heart_v3b25.bit"] and preflight.get("hwh_sha256")==PAIR_HASHES["heart_v3b25.hwh"],
        one_download=cleanup.get("download_attempts")==1,
        joint_cleanup=cleanup.get("cleanup_complete") is True and joint.get("inherited_cleanup_complete") is True,
        no_wrapper_error=wrapper_error is None and original.get("wrapper_error") is None and joint.get("wrapper_error") is None,
        effective25=(summary.get("raw_hz"),summary.get("processing_hz"),summary.get("adc_hz"),summary.get("fifo_sample_average"))==(25,25,50,2),
        full_duration=summary.get("elapsed_seconds",0)>=60. and summary.get("stop_reason")=="duration_complete",
        inputs_unchanged=bool(inputs_unchanged))
    return dict(schema="v3b25_joint_heart_trial_v1",joint_heart_static_pilot_completed=all(checks.values()),
                checks=checks,wrapper_error=wrapper_error,**FLAGS,camera_started=False,hdmi_started=False,
                vision_frame_transferred=False,video_on_joint_passed=False,concurrent60_passed=False,
                accuracy_verified=False,strict_realtime_verified=False,
                bit_hwh_sha256=dict(PAIR_HASHES),
                scope_cn="联合电路25Hz心率单测；原模板中的原Overlay/位流不变/raw50仅描述冻结参考，不是本次硬件身份。")
