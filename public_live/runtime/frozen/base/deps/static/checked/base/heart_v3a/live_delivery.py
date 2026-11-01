"""追加实时身份，不改已发布基manifest、bit、HWH或冻结主链。"""
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import zipfile
from .delivery import validate_bundle, RUNTIME_FILES

BASE_MANIFEST_SHA256 = "f9982dce7124067260bf6a9a1e8b8f73a518448e8e75665c5340ca111d1471a5"
BIT_SHA256 = "dd1a4f7704b8bc236c6d232f3bdec812dbb941dd2a328aa1e5be9ad9bccead20"
HWH_SHA256 = "d8a50cb8dc5ff69e51e20b91d0dbc38ca22c7e46d7df0c6f5b630e2d28627548"
LIVE_FILES = {name: name for name in ("heart_v3a/live/__init__.py", "heart_v3a/live/contracts.py",
    "heart_v3a/live/capture.py", "heart_v3a/live/journal.py", "heart_v3a/live/session.py",
    "heart_v3a/live/view.py", "heart_v3a/live/board.py", "heart_v3a/live/processing.py",
    "heart_v3a/live/single_sample.py", "heart_v3a/live/numpy_compat.py", "heart_v3a/live/history_fast.py", "heart_v3a/live_delivery.py",
    "run_v3a_live.py", "run_v3a_sos_check.py", "run_v3a_history_check.py", "heart_v3a_live_notebook.ipynb",
    "heart_v3a/live/process_chain.py", "heart_v3a/live/isolated.py", "run_v3a_isolated_live.py",
    "heart_v3a/live/statistics_fast.py", "run_v3a_statistics_check.py")}
LIVE_FILES["README_live_zh.md"] = "docs/v3a-live-50hz-usage-zh.md"
LIVE_FILES["README_isolated_pilot_zh.md"] = "docs/v3a-isolated-live-pilot-zh.md"
LIVE_FILES["README_statistics_zh.md"] = "docs/v3a-statistics-fast-zh.md"
WORK_NOTEBOOK = "heart_v3a_live_work.ipynb"
CAPACITIES = dict(raw_batches=8, batch_records=32, processing_records=250,
    result_records=250, history_records=500, terminal_batches=1)
FLAGS = ("board_tested", "live_50hz_passed", "auto_beta_effect_passed", "board_ddr_verified", "v3a_complete")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def confined_path(bundle, relative):
    root = Path(bundle).resolve()
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError("实时交付相对路径不合法")
    rel = PurePosixPath(relative)
    if rel.is_absolute() or PureWindowsPath(relative).drive or any(part in (".", "..") for part in relative.split("/")):
        raise ValueError("实时交付路径逃逸")
    path = root.joinpath(*rel.parts)
    if any(parent.is_symlink() for parent in (path, *path.parents) if parent != root.parent):
        raise ValueError("实时交付不允许symlink")
    if not path.resolve().is_relative_to(root):
        raise ValueError("实时交付路径逃逸")
    return path


def live_source_hashes(arena):
    return {name: digest(confined_path(arena, source)) for name, source in LIVE_FILES.items()}


def _base_identity(bundle):
    root = Path(bundle).resolve()
    expected = {"manifest.json": BASE_MANIFEST_SHA256, "heart_v3a.bit": BIT_SHA256, "heart_v3a.hwh": HWH_SHA256}
    for name, sha in expected.items():
        path = confined_path(root, name)
        if not path.is_file() or digest(path) != sha:
            raise ValueError("不可变基包身份不符：" + name)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name in manifest["file_hashes"]:
        confined_path(root, name)
    return validate_bundle(root)


def create_live_bundle(base, arena, target, *, tested_source_hashes):
    base, arena, target = Path(base).resolve(), Path(arena).resolve(), Path(target).resolve()
    if target.exists() or target.is_relative_to(base) or target == arena:
        raise ValueError("已有／基包内目标不得覆盖")
    info = _base_identity(base)
    current = live_source_hashes(arena)
    if current != tested_source_hashes:
        raise ValueError("新增源码闭包与被测摘要不一致")
    # 旧运行闭包必须与基包一致；不从工作区偷换旧驱动或配置。
    for name in (*RUNTIME_FILES, "heart_axi_live.py", "heart_axi_capture_50hz.py"):
        source = arena / name
        if name.startswith("heart_axi_"):
            source = arena.parent / name
        if not source.is_file() or digest(source) != info["file_hashes"][name]:
            raise ValueError("现有运行源与基包不同：" + name)
    if set(current) & (set(info["file_hashes"]) | {"manifest.json"}):
        raise ValueError("新增闭包覆盖旧追踪文件")
    target.mkdir(parents=True, exist_ok=False)
    for name in (*info["file_hashes"], "manifest.json"):
        destination = confined_path(target, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(confined_path(base, name), destination)
    for name, source in LIVE_FILES.items():
        destination = confined_path(target, name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(confined_path(arena, source), destination)
    # work 是可写运行产物，初始内容必须来自被测模板，但保存输出不影响模板身份。
    shutil.copy2(confined_path(target, "heart_v3a_live_notebook.ipynb"),
                 confined_path(target, WORK_NOTEBOOK))
    if live_source_hashes(arena) != current:
        raise ValueError("复制期间被测源码改变，拒绝发布")
    manifest = dict(schema="v3a_live_bundle_v1", base_manifest_sha256=BASE_MANIFEST_SHA256,
        bit_sha256=BIT_SHA256, hwh_sha256=HWH_SHA256, file_hashes=current,
        tested_source_hashes=dict(tested_source_hashes), capacities=CAPACITIES,
        beta_int=32212255, scope_cn="仅50Hz采集／原始优先记录／固定NLMS邮箱／冻结PS／中文显示；无摄像头及自动调参",
        **{key: False for key in FLAGS})
    with (target / "live-manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    return validate_live_bundle(target)


def validate_live_bundle(bundle):
    root = Path(bundle).resolve()
    _base_identity(root)
    manifest = json.loads(confined_path(root, "live-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "v3a_live_bundle_v1" or any(manifest.get(key) is not False for key in FLAGS):
        raise ValueError("实时包schema／未验门不符")
    for name, sha in (("base_manifest_sha256", BASE_MANIFEST_SHA256), ("bit_sha256", BIT_SHA256), ("hwh_sha256", HWH_SHA256)):
        if manifest.get(name) != sha:
            raise ValueError("附加身份与基包不符")
    files = manifest.get("file_hashes", {})
    if set(files) != set(LIVE_FILES) or manifest.get("tested_source_hashes") != files:
        raise ValueError("实时运行闭包／被测摘要不完整")
    if manifest.get("capacities") != CAPACITIES or manifest.get("beta_int") != 32212255:
        raise ValueError("工程容量／固定算法参数不符")
    for name, sha in files.items():
        path = confined_path(root, name)
        if not path.is_file() or digest(path) != sha:
            raise ValueError("实时文件缺失或哈希不符：" + name)
    return manifest


def write_live_zip(bundle):
    root = Path(bundle).resolve()
    manifest = validate_live_bundle(root)
    old = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    work = confined_path(root, WORK_NOTEBOOK)
    if not work.is_file() or digest(work) != manifest["file_hashes"]["heart_v3a_live_notebook.ipynb"]:
        raise ValueError("待打包工作副本必须等于被测原始模板")
    archive = root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as stream:
        for name in sorted(set(old["file_hashes"]) | set(manifest["file_hashes"]) | {"manifest.json", "live-manifest.json", WORK_NOTEBOOK}):
            stream.write(confined_path(root, name), arcname=name)
    return archive
