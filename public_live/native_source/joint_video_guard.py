"""Stdlib-only file identity and bounded-scope video report assessment."""
import hashlib
import json
from pathlib import Path

if __package__:
    from .joint_owner import PAIR_HASHES,verify_pair
else:
    from joint_owner import PAIR_HASHES,verify_pair

OWNER_SHA="5ec45d6e8a37037591734fa8a92e6bd5129e648c54cca1e5485a6e5fda563562"
REFERENCE_SHA="cc75be1d71f100a383118367d82a230ea4ea853e8c12d2d87a43b180b02a8df9"
DRIVER_HASHES={
    "hierarchies.py":"528106d7ea2c95cfd64ec27f2696f9daab76fb2c96341f1a48cd04b211f85950",
    "dma.py":"94346a4ae6a7a7f9e4b78887179e2a55ff821c7ed3724b584a7bb4c228fea30f",
    "dvi.py":"ed46cd6259037474762725d654a9a7e266d02d2052d8202b37a58085b4520cea",
    "pipeline.py":"a176db13a567ffe080af7e4691a8ce49382450fcb47c1bea6bca76422b37b7c3",
    "common.py":"2c4d6c2cb3ede0aca97aa2980dec7d5147ce6f4d446635ddd7dd1e894282cbf7",
}
TOP_FILES=set(PAIR_HASHES)|{"joint-artifacts.json","joint_owner.py","vision_reference.py",
    "joint_video_transport.py","joint_video_runtime.py","joint_video_worker.py","joint_video_guard.py",
    "run_joint_video.py","README_VIDEO.md"}
FLAGS=dict.fromkeys(("live_25hz_passed","live_50hz_passed","auto_beta_effect_passed","board_ddr_verified",
    "limits_frozen","run_acceptance_passed","v3a_complete","full_v3b_acceptance_passed","accuracy_verified",
    "strict_realtime_verified","concurrent60_passed","video_on_joint_passed","display_acceptance_passed"),False)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path,value):
    with Path(path).open("x",encoding="utf-8") as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)


def notebook_code_hash(path):
    book=json.loads(Path(path).read_text(encoding="utf-8"))
    cells=["".join(c["source"]) for c in book["cells"] if c["cell_type"]=="code"]
    return hashlib.sha256(json.dumps(cells,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def verify_package(root):
    root=Path(root).resolve()
    doc=json.loads((root/"joint-video-manifest.json").read_text(encoding="utf-8"))
    if (doc.get("schema")!="v3b25_joint_video_package_v1" or set(doc.get("files",{}))!=TOP_FILES
            or doc.get("formal_seconds")!=20 or doc.get("target_application_fps")!=15
            or doc.get("driver_hashes")!=DRIVER_HASHES or any(doc.get(k) is not False for k in FLAGS)):
        raise ValueError("joint video package scope/driver/file identity mismatch")
    for name,digest in doc["files"].items():
        p=root/name
        if p.is_symlink() or not p.is_file() or sha(p)!=digest:
            raise ValueError("joint video file hash mismatch: "+name)
    if sha(root/"joint_owner.py")!=OWNER_SHA or sha(root/"vision_reference.py")!=REFERENCE_SHA:
        raise ValueError("frozen joint owner/integer reference changed")
    if notebook_code_hash(root/"JointVideo.ipynb")!=doc.get("notebook_code_sha256"):
        raise ValueError("joint video executable Notebook cells changed")
    verify_pair(root)
    return dict(bundle_validated=True,hardware_accessed=False,heart_capture_started=False,
        camera_started=False,hdmi_started=False,formal_seconds=20,target_application_fps=15,
        package_manifest_sha256=sha(root/"joint-video-manifest.json"),**FLAGS)


def assess_worker(report):
    m=report.get("metrics") or {}
    c=report.get("cleanup") or {}
    j=c.get("joint") or {}
    identity=(report.get("identity") or {}).get("joint_identity") or {}
    metadata=identity.get("metadata") or {}
    n=m.get("completed_frames",0)
    ids=(identity.get("nlms") or {}).get("id")==0x4e4c3304 and (identity.get("vision") or {}).get("id")==0x56334231
    return dict(full_duration=report.get("stop_reason")=="duration_complete" and
            report.get("requested_formal_seconds")==20 and (m.get("formal_elapsed_seconds") or 0)>=20,
        no_fault=report.get("fault") is None and report.get("publication_error") is None,
        joint_identity=ids and metadata.get("windows")==13 and metadata.get("vdma_frame_stores")==4,
        one_download=j.get("download_attempts")==1,
        exact_counts=n>=3 and n==m.get("records_saved")==c.get("captured_frames")==c.get("submitted_frames")==c.get("vision_completed_frames"),
        same_frame_reference=m.get("same_frame_mismatches")==0 and m.get("same_frame_matches")==n and m.get("valid_difference_frames",0)>0,
        cleanup=c.get("cleanup_complete") is True and c.get("quarantine_required") is False and j.get("cleanup_complete") is True,
        inputs_unchanged=report.get("inputs_unchanged") is True,
        formal_flags_false=all(report.get(k) is False for k in FLAGS))


def audit_frames(directory,worker):
    checks=dict(parse_complete=False,file_hash=False,counts=False,source_alignment=False,same_frame_verified=False)
    result=dict(checks=checks,rows=0,error=None)
    try:
        path=Path(directory)/"frames.jsonl"
        data=path.read_bytes()
        rows=[json.loads(line) for line in data.decode("utf-8").splitlines()]
        result["rows"]=len(rows)
        checks["parse_complete"]=bool(data.endswith(b"\n") or not data)
        checks["file_hash"]=hashlib.sha256(data).hexdigest()==worker.get("frames_sha256")
        metrics=worker.get("metrics") or {}
        checks["counts"]=len(rows)>=3 and len(rows)==metrics.get("records_saved")==metrics.get("completed_frames")
        epochs={r["vision"]["epoch"] for r in rows}
        times=[r["read_completed_ns"] for r in rows]
        checks["source_alignment"]=bool(rows) and len(epochs)==1 and all(
            r["source_sequence"]==i and r["vision"]["source_sequence"]==i and r["vision"]["frame_index"]==i
            for i,r in enumerate(rows)) and all(b>a for a,b in zip(times,times[1:]))
        valid=sum(r["vision"]["difference_valid"] is True for r in rows)
        checks["same_frame_verified"]=bool(rows) and valid>0 and valid==metrics.get("valid_difference_frames") and all(
            r["same_frame_equal"] is True and r["hdmi_submitted"] is True and r["mismatches"]=={} for r in rows)
    except Exception as exc:
        result["error"]=dict(type=type(exc).__name__,message=str(exc))
    return result
