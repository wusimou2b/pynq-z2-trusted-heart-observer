"""One-shot ownership of the reviewed joint bit. No hardware import at module load.

This foundation binds raw control windows only. It does not start heart capture,
camera, HDMI, DMA, or the old loaders. Metadata checks are not silicon tests.
"""
import hashlib
import json
from pathlib import Path
import platform
import sys
import time


PAIR_HASHES = {
    "heart_v3b25.bit":"aacedae31a82010d24f086aa8815250282c97ecfd1d5b1b551b0a7bf20fb1cd5",
    "heart_v3b25.hwh":"2f17d4f4eb255ced45f9f27bfbd2600767d77faab5144365fb33ec3510487866",
}
PACKAGE_FILES = set(PAIR_HASHES) | {"joint-artifacts.json", "joint_owner.py", "run_joint_identity.py",
                                       "JointIdentity.ipynb", "README_BOARD.md"}
WINDOWS = {
    "axi_fifo_mm_s_0":(0x43c00000,"xilinx.com:ip:axi_fifo_mm_s:4.3"),
    "axi_iic_0":(0x41600000,"xilinx.com:ip:axi_iic:2.1"),
    "nlms_axi_0":(0x43c10000,"heart.local:signal:nlms_axi_lite:1.0"),
    "vision_0":(0x43c80000,"v3b25.local:vision:vision_axi_lite:1.0"),
    "vision_dma":(0x44a00000,"xilinx.com:ip:axi_dma:7.1"),
    "vision_control":(0x41240000,"xilinx.com:ip:axi_gpio:2.0"),
    "hdmi_vdma":(0x43000000,"xilinx.com:ip:axi_vdma:6.3"),
    "hdmi_out/pixel_unpack":(0x43c70000,"xilinx.com:hls:pixel_unpack:1.0"),
    "hdmi_out/color_convert":(0x43c60000,"xilinx.com:hls:color_convert:1.0"),
    "hdmi_out/frontend/vtc_out":(0x43c20000,"xilinx.com:ip:v_tc:6.2"),
    "hdmi_out/frontend/axi_dynclk":(0x43c90000,"digilentinc.com:ip:axi_dynclk:1.0"),
    "hdmi_out/frontend/hdmi_out_hpd_video":(0x41230000,"xilinx.com:ip:axi_gpio:2.0"),
    "system_interrupts":(0x41800000,"xilinx.com:ip:axi_intc:4.1"),
}
DMA_NAMES = ("vision_dma", "hdmi_vdma")
DMA_ERROR_MASKS = {"vision_dma":0x770, "hdmi_vdma":0xff0}
IDS = {"nlms_axi_0":0x4e4c3304, "vision_0":0x56334231}


def _hash(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("missing/symlink bundle member: "+path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_pair(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"joint-artifacts.json").read_text(encoding="utf-8"))
    if (manifest.get("schema") != "v3b25_joint_artifacts_v1" or
            manifest.get("purpose") != "controlled_board_trials_only" or manifest.get("files") != PAIR_HASHES):
        raise ValueError("unreviewed joint artifact identity")
    for name, digest in PAIR_HASHES.items():
        if _hash(directory/name) != digest:
            raise ValueError("joint artifact hash mismatch: "+name)
    return dict(pair_integrity_verified=True, hardware_accessed=False,
                full_v3b_acceptance_passed=False)


def verify_bundle(directory):
    directory = Path(directory)
    manifest = json.loads((directory/"joint-owner-manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("schema") != "v3b25_joint_identity_package_v1" or
            set(manifest.get("files", {})) != PACKAGE_FILES):
        raise ValueError("wrong single-owner package file map")
    for name, digest in manifest["files"].items():
        if _hash(directory/name) != digest:
            raise ValueError("single-owner package hash mismatch: "+name)
    return dict(**verify_pair(directory), entry="manual_joint_identity_only",
                bit_hwh_sha256=dict(PAIR_HASHES), package_manifest_sha256=_hash(directory/"joint-owner-manifest.json"),
                heart_capture_started=False, camera_started=False, hdmi_started=False,
                concurrent_runtime_ready=False, board_ddr_verified=False)


def validate_description(description):
    """Check PYNQ's parsed map before any download or attribute-driver binding."""
    for name, (address, vlnv) in WINDOWS.items():
        item = description.get(name, {})
        if (item.get("phys_addr") != address or item.get("addr_range") != 65536 or item.get("type") != vlnv):
            raise ValueError("runtime IP metadata mismatch: "+name)
    for name in DMA_NAMES:
        params = description[name].get("parameters", {})
        expected = dict(C_INCLUDE_MM2S="1", C_INCLUDE_S2MM="0", C_INCLUDE_SG="0",
                        C_M_AXIS_MM2S_TDATA_WIDTH="32", C_M_AXI_MM2S_DATA_WIDTH="32")
        if name == "hdmi_vdma":
            expected.update(C_NUM_FSTORES="4", C_MM2S_GENLOCK_MODE="1")
        if any(str(params.get(key)) != value for key, value in expected.items()):
            raise ValueError("runtime DMA configuration mismatch: "+name)
    return dict(windows=13, vdma_frame_stores=4, video_mm2s_only=True)


def require_board():
    if sys.platform != "linux" or platform.machine() != "armv7l":
        raise RuntimeError("仅在PYNQ-Z2板端Linux/armv7l运行；禁止在电脑启动硬件")


class BoardLease:
    """Same advisory lock as frozen heart; old video loaders do not honor it."""
    def __init__(self, path="/tmp/heart_v3a_live.lock"):
        self.path, self.stream = Path(path), None

    def acquire(self):
        import fcntl
        stream = self.path.open("a", encoding="utf-8")
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            stream.close()
            raise RuntimeError("另一进程持有心率硬件锁；不启动联合电路")
        self.stream = stream

    def release(self):
        if self.stream is not None:
            import fcntl
            try:
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            finally:
                self.stream.close()
                self.stream = None


class PynqHardware:
    """Lazy physical boundary; no VideoOut/VDMA driver constructor side effects."""
    def __init__(self, bit_path):
        require_board()
        import pynq
        if pynq.__version__ != "3.1.1":
            raise RuntimeError("当前入口只核对过PYNQ 3.1.1，保留输出，不自动兼容/重试")
        from pynq import MMIO, Overlay
        self._mmio_factory = MMIO
        self._overlay = Overlay(str(bit_path), download=False)
        self.description = self._overlay.ip_dict

    def download(self):
        self._overlay.download()

    def is_loaded(self):
        return self._overlay.is_loaded()

    def mmio(self, name):
        return self._mmio_factory(WINDOWS[name][0], 65536)


class JointOwner:
    """One lifecycle; hardware/lease boundaries also support offline policy tests."""
    def __init__(self, directory, hardware_factory=PynqHardware, lease=None, *,
                 halt_timeout=2.0, on_event=None):
        if not 0 < halt_timeout <= 10:
            raise ValueError("bounded positive DMA halt timeout required")
        self.directory = Path(directory)
        self._factory = hardware_factory
        self._lease = lease if lease is not None else BoardLease()
        self._halt_timeout = halt_timeout
        self._on_event = on_event
        self._lease_held = self._downloaded = self._trusted = False
        self._hardware, self._io, self._cleanup = None, {}, None
        self.download_attempts, self.state = 0, "new"

    def _event(self, stage):
        if self._on_event is not None:
            self._on_event(dict(stage=stage, monotonic_ns=time.monotonic_ns()))

    def open(self):
        if self.state != "new":
            raise RuntimeError("single owner already attempted; do not retry")
        self.state = "opening"
        self._event("checking_pair")
        verify_pair(self.directory)
        self._lease.acquire()
        self._lease_held = True
        self._event("constructing_metadata_only_overlay")
        self._hardware = self._factory(self.directory/"heart_v3b25.bit")
        validate_description(self._hardware.description)
        self.download_attempts += 1
        self._event("explicit_download_attempt")
        self._hardware.download()
        self._downloaded = True
        if not self._hardware.is_loaded():
            raise RuntimeError("download returned but joint Overlay is not current")
        self._event("binding_raw_control_windows")
        for name in (*IDS, "vision_control", *DMA_NAMES):
            self._io[name] = self._hardware.mmio(name)
        identities = {}
        for name, expected in IDS.items():
            ident, version = int(self._io[name].read(0)), int(self._io[name].read(4))
            if ident != expected or version != 0x10000:
                raise RuntimeError("silicon identity mismatch: "+name)
            identities["nlms" if name == "nlms_axi_0" else "vision"] = dict(id=ident, version=version)
        self._trusted = True
        halted = self._halt_paths()
        if not all(item["halted"] for item in halted.values()):
            raise RuntimeError("video DMA not halted at identity entry")
        if any(item["error_bits"] for item in halted.values()):
            raise RuntimeError("video DMA error at identity entry; status not cleared")
        identities["vision_reset"] = self._hold_vision_reset()
        identities.update(metadata=validate_description(self._hardware.description), stopped_dma=halted)
        self.state = "bound"
        self._event("joint_identity_bound_no_capture")
        return identities

    def _halt_paths(self):
        results = {}
        for name in DMA_NAMES:
            item = dict(halted=False)
            results[name] = item
            try:
                if not self._hardware.is_loaded():
                    raise RuntimeError("joint Overlay changed; refuse MMIO")
                io = self._io[name]
                control = int(io.read(0))
                io.write(0, control & ~1)
                deadline = time.monotonic()+self._halt_timeout
                while True:
                    status, stopped_control = int(io.read(4)), int(io.read(0))
                    if status & 1 and not stopped_control & 1:
                        item.update(halted=True, status=status, control=stopped_control,
                                    error_bits=status & DMA_ERROR_MASKS[name])
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("MM2S halt not confirmed: "+name)
                    time.sleep(0.001)
            except Exception as exc:
                item["error"] = dict(type=type(exc).__name__, message=str(exc))
        return results

    def _hold_vision_reset(self):
        if not self._hardware.is_loaded():
            raise RuntimeError("joint Overlay changed; refuse reset")
        self._io["vision_control"].write(0, 0)
        if self._io["vision_control"].read(0) & 1:
            raise RuntimeError("vision packet reset not held")
        core = self._io["vision_0"]
        epoch = int(core.read(0x18))
        core.write(8, 4)
        after = int(core.read(0x18))
        if after != (epoch+1) & 0xffffffff:
            raise RuntimeError("vision reset epoch did not advance")
        status = int(core.read(0x0c))
        if status != 0:
            raise RuntimeError("vision mailbox not idle after reset")
        return dict(packet_reset_held=True, epoch_before=epoch, epoch_after=after, mailbox_status=status)

    def close(self):
        """No restoration/download, no buffer free, and no false cleanup on failure."""
        if self._cleanup is not None:
            return self._cleanup
        result = dict(download_attempts=self.download_attempts, cleanup_complete=False, dma={}, errors=[],
                      cleanup_scope="owned_video_dma_and_vision_reset_only", old_overlay_restored=False,
                      hdmi_link_state_tested=False)
        try:
            if not self.download_attempts:
                result.update(cleanup_complete=True, hardware_state="no_download_attempted")
            elif not self._downloaded:
                result["hardware_state"] = "unknown_after_download_failure"
            elif not self._trusted:
                result["hardware_state"] = "unconfirmed_identity_or_binding"
            elif not self._hardware.is_loaded():
                result["hardware_state"] = "overlay_changed_no_cleanup_writes"
            else:
                result["dma"] = self._halt_paths()
                if all(item["halted"] for item in result["dma"].values()):
                    result["vision_reset"] = self._hold_vision_reset()
                    result.update(cleanup_complete=True, hardware_state="joint_retained_dma_halted_vision_reset")
                else:
                    result["hardware_state"] = "unconfirmed_dma_halt"
        except BaseException as exc:
            result["errors"].append(dict(type=type(exc).__name__, message=str(exc)))
            result["hardware_state"] = "cleanup_error"
        finally:
            if self._lease_held:
                try:
                    self._lease.release()
                except BaseException as exc:
                    result["errors"].append(dict(type=type(exc).__name__, message=str(exc)))
                    result["cleanup_complete"] = False
                self._lease_held = False
            self.state = "closed"
            self._cleanup = result
        return result
