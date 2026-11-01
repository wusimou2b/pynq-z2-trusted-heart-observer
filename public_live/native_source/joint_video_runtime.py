"""Camera + finite vision + explicit HDMI binding under the unchanged owner."""
import hashlib
import importlib
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np

if __package__:
    from .joint_owner import JointOwner,BoardLease,PynqHardware,require_board
    from .joint_video_transport import VisionPort,DeadlineMMIO,UserStop,validate_frame
    from .joint_video_guard import DRIVER_HASHES
    from ..vision_reference import VisionReference
else:
    from joint_owner import JointOwner,BoardLease,PynqHardware,require_board
    from joint_video_transport import VisionPort,DeadlineMMIO,UserStop,validate_frame
    from joint_video_guard import DRIVER_HASHES
    from vision_reference import VisionReference


STAT_FIELDS=("pixel_count","luma_sum","luma_min","luma_max","difference_valid","diff_sum","diff_max","reason")


def load_board_api():
    require_board()
    import pynq
    if pynq.__version__!="3.1.1":
        raise RuntimeError("joint video entry requires reviewed PYNQ3.1.1")
    import pynq.lib.video
    actual={}
    for name,expected in DRIVER_HASHES.items():
        module=importlib.import_module("pynq.lib.video."+name[:-3])
        path=Path(module.__file__)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=expected:
            raise RuntimeError("installed video source changed; no hardware started: "+name)
        actual[name]=dict(path=str(path),sha256=digest)
    import cv2
    from pynq.lib.video import VideoMode
    from pynq.lib.video.hierarchies import VideoOut
    return SimpleNamespace(cv2=cv2,allocate=pynq.allocate,VideoMode=VideoMode,VideoOut=VideoOut,
        hardware_factory=PynqHardware,lease_factory=BoardLease,driver_identity=actual)


class DeferredLease:
    """Delay JointOwner's unlock until its video buffers can safely be released."""
    def __init__(self,lease):self.lease,self.held=lease,False
    def acquire(self):self.lease.acquire();self.held=True
    def release(self):pass
    def finish(self):
        if self.held:self.lease.release();self.held=False


def describe(exc,stage):
    return dict(stage=stage,type=type(exc).__name__,message=str(exc))


class VideoResources:
    """Single sequential owner, one vision buffer, bounded installed HDMI cache.

    On unconfirmed halt, references and the real advisory lock remain held. The
    worker must then stay alive (quarantine) rather than let CMA destructors run.
    """
    def __init__(self,directory,*,cancelled,on_event,api_factory=load_board_api):
        self.directory=Path(directory)
        self.cancelled,self.on_event,self.api_factory=cancelled,on_event,api_factory
        self.owner=self.api=self.lease=self.camera=self.hdmi=self.vdma=self.guard=None
        self.buffer=self.pending=self.port=None
        self.reference=VisionReference()
        self.stage="new"
        self.captured=self.submitted=0
        self.last_frame=None
        self._cleanup=None

    def _stage(self,name):
        self.stage=name
        self.on_event(dict(stage=name,monotonic_ns=time.monotonic_ns()))

    def _available(self):
        if self.cancelled():raise UserStop("user stop requested")
        if self.owner is not None and self.owner.state=="bound" and not self.owner._hardware.is_loaded():
            raise RuntimeError("joint Overlay changed; no video action allowed")

    def open(self):
        if self.stage!="new":raise RuntimeError("video resources already attempted")
        self._stage("imports_and_driver_source_check")
        self.api=self.api_factory()
        self.lease=DeferredLease(self.api.lease_factory())
        self.owner=JointOwner(self.directory,self.api.hardware_factory,self.lease,on_event=self.on_event)
        self._stage("joint_owner_open")
        identity=self.owner.open()
        self._available()
        self._stage("camera_startup")
        cv=self.api.cv2
        self.camera=cv.VideoCapture("/dev/video0",cv.CAP_V4L2)
        if not self.camera.isOpened():raise RuntimeError("camera /dev/video0 could not open; no retry")
        self.camera.set(cv.CAP_PROP_FRAME_WIDTH,640)
        self.camera.set(cv.CAP_PROP_FRAME_HEIGHT,480)
        self.camera.set(cv.CAP_PROP_FOURCC,cv.VideoWriter_fourcc(*"YUYV"))
        ok,first=self.camera.read()
        if not ok:raise RuntimeError("camera startup read failed; no retry")
        validate_frame(first)
        fourcc=int(self.camera.get(cv.CAP_PROP_FOURCC))
        camera=dict(device="/dev/video0",opencv_version=cv.__version__,image_size=[640,480],
            fourcc="".join(chr((fourcc>>(8*i))&255) for i in range(4)),
            driver_reported_fps_not_measured=self.camera.get(cv.CAP_PROP_FPS),startup_read_not_in_formal_counts=True)
        if camera["fourcc"]!="YUYV":raise RuntimeError("camera did not accept reviewed YUYV format")
        del first
        self._available()
        self._stage("explicit_hdmi_binding")
        view=self.owner._hardware._overlay
        self.vdma=view.hdmi_vdma
        if self.vdma.framecount!=4 or hasattr(self.vdma,"readchannel"):
            raise RuntimeError("HDMI VDMA must have four MM2S-only frame stores")
        channel=self.vdma.writechannel
        self.guard=DeadlineMMIO(channel._mmio,is_loaded=self.owner._hardware.is_loaded)
        channel._mmio=self.guard
        if hasattr(channel._frames,"_mmio"):channel._frames._mmio=self.guard
        self.hdmi=self.api.VideoOut(view.hierarchy_dict["hdmi_out"],vdma=self.vdma)
        mode=self.api.VideoMode(640,480,24,60)
        self._stage("hdmi_configure")
        with self.guard.budget(5,"configure"):self.hdmi.configure(mode)
        self._available()
        self._stage("hdmi_start")
        with self.guard.budget(3,"start"):self.hdmi.start()
        raw=self.owner._io["hdmi_vdma"]
        if (raw.read(0)&2 or raw.read(0x54)!=1920 or raw.read(0x58)&0xffffff!=1920 or raw.read(0x50)!=480):
            raise RuntimeError("HDMI geometry/parking configuration readback mismatch")
        self._available()
        self._stage("vision_allocate_and_release_reset")
        self.buffer=self.api.allocate(shape=(480,640,4),dtype=np.uint8,cacheable=True)
        self.port=VisionPort(self.owner._io["vision_0"],self.owner._io["vision_dma"],
            self.owner._io["vision_control"],self.buffer,is_loaded=self.owner._hardware.is_loaded,cancelled=self.cancelled)
        self.port.start()
        self._stage("ready")
        return dict(joint_identity=identity,camera=camera,driver_identity=self.api.driver_identity,
            hdmi_mode=dict(width=640,height=480,bits_per_pixel=24,configured_refresh_hz_not_camera_fps=60),
            buffer_policy="one BGRX vision buffer; original four-slot HDMI channel/cache; no image history")

    def process_frame(self,*,sequence,timestamp_ns=None):
        self._available()
        self._stage("camera_read")
        ok,bgr=self.camera.read()
        if not ok:raise RuntimeError("camera read failed; no retry")
        read_ns=time.monotonic_ns() if timestamp_ns is None else timestamp_ns
        validate_frame(bgr)
        self.captured+=1
        self._stage("same_frame_reference")
        expected=self.reference.process(bgr,sequence=sequence,timestamp_ns=read_ns)
        self._stage("finite_vision_transfer")
        actual=self.port.process(bgr,sequence=sequence,timestamp_ns=read_ns)
        differences={k:dict(reference=getattr(expected,k),pl=actual[k]) for k in STAT_FIELDS if getattr(expected,k)!=actual[k]}
        self.last_frame=dict(source_sequence=sequence,read_completed_ns=read_ns,vision=actual,
                             same_frame_equal=not differences,mismatches=differences,hdmi_submitted=False)
        if differences:raise RuntimeError("same-frame integer reference mismatch: "+repr(differences))
        self._available()
        self._stage("hdmi_submit")
        shown=bgr.copy()
        cv=self.api.cv2
        cv.rectangle(shown,(160,120),(479,359),(0,255,0),1)
        cv.putText(shown,"VIDEO ONLY | HEART OFF | seq="+str(sequence),(10,22),cv.FONT_HERSHEY_SIMPLEX,.48,(0,255,255),1)
        difference=str(actual["diff_sum"]) if actual["difference_valid"] else "N/A ("+actual["reason"]+")"
        cv.putText(shown,"PL ROI luma="+str(actual["luma_sum"])+" diff="+difference,(10,44),cv.FONT_HERSHEY_SIMPLEX,.45,(0,255,255),1)
        self.pending=self.hdmi.newframe()
        if self.pending.shape!=(480,640,3) or self.pending.dtype!=np.dtype("uint8"):
            raise RuntimeError("HDMI frame is not packed BGR24")
        self.pending[:]=shown
        with self.guard.budget(1,"frame submit"):
            while not int(self.guard.read(4))&0x1000:
                self._available()
                time.sleep(.001)
            self.hdmi.writeframe(self.pending)
        self.pending=None
        self.submitted+=1
        self.last_frame["hdmi_submitted"]=True
        return dict(self.last_frame)

    def close(self):
        if self._cleanup is not None:return self._cleanup
        result=dict(cleanup_complete=False,camera_release_returned=self.camera is None,
            hdmi_close_returned=self.hdmi is None,buffers_released=False,lease_released=False,
            quarantine_required=False,errors=[],captured_frames=self.captured,submitted_frames=self.submitted,
            vision_completed_frames=self.port.completed if self.port else 0,last_frame=self.last_frame)
        def attempt(stage,operation):
            try:operation();return True
            except BaseException as exc:result["errors"].append(describe(exc,stage));return False
        if self.camera is not None:result["camera_release_returned"]=attempt("camera_release",self.camera.release)
        if self.hdmi is not None:
            def stop_hdmi():
                with self.guard.budget(3,"close"):self.hdmi.close()
            result["hdmi_close_returned"]=attempt("hdmi_close",stop_hdmi)
        joint=self.owner.close() if self.owner is not None else dict(cleanup_complete=True,download_attempts=0,dma={},errors=[])
        result["joint"]=joint
        halted=(not joint["download_attempts"] or (len(joint.get("dma",{}))==2 and
                  all(x.get("halted") is True for x in joint["dma"].values())))
        owns_memory=self.buffer is not None or self.hdmi is not None or self.pending is not None
        if halted:
            def free_buffers():
                if self.hdmi is not None:
                    with self.guard.budget(2,"release stopped frame cache",allow_halted_errors=True):
                        channel=self.vdma.writechannel
                        for i in range(len(channel._frames)):channel._frames[i]=None
                    if not result["hdmi_close_returned"]:self.hdmi._hdmi.stop()
                if self.pending is not None:self.pending.freebuffer();self.pending=None
                if self.buffer is not None:self.buffer.freebuffer();self.buffer=None
                if self.vdma is not None and hasattr(self.vdma.writechannel,"_cache"):
                    self.vdma.writechannel._cache.clear()
            result["buffers_released"]=attempt("release_halted_buffers",free_buffers)
            if self.lease is not None:result["lease_released"]=attempt("lease_release",self.lease.finish)
            else:result["lease_released"]=True
        else:
            result["buffers_released"]=not owns_memory
            result["quarantine_required"]=owns_memory
            if not owns_memory and self.lease is not None:
                result["lease_released"]=attempt("lease_release_without_owned_buffers",self.lease.finish)
        result["dma_halt_confirmed"]=bool(halted)
        result["cleanup_complete"]=bool(joint["cleanup_complete"] and halted and not result["errors"] and
            result["camera_release_returned"] and result["hdmi_close_returned"] and
            result["buffers_released"] and result["lease_released"] and
            not any(x.get("error_bits",0) for x in joint.get("dma",{}).values()))
        self._cleanup=result
        return result
