"""Child-only physical video adapters; no hardware import at module load."""
from pathlib import Path
import time
from types import SimpleNamespace as N
import hashlib
import importlib.util
import sys

VIDEO_PORTS=('vision_0','vision_control','vision_dma','hdmi_vdma','display_dma','yuyv_control')


def load_dependencies(*,root,check,record):
    """Original imports/API only; all actual resource constructors stay in prepare."""
    check();record('python_video_imports_begin')
    from main_spatial_owner import Hardware,validate_description
    from hybrid_display import HybridResources
    from yuyv_runtime import load_api
    from shadow_fusion import ShadowFusion
    from hdmi_dashboard_model import DashboardModel
    from continuous_runtime import make_video_class
    # Spawn must not depend on a prior Notebook/heart bootstrap's sys.path.
    # This exact original file was checked by the full child manifest.
    window_path=(Path(root)/'frozen/base/effective25_gc_window.py').resolve(strict=True)
    window=sys.modules.get('effective25_gc_window')
    if window is None:
        definition=importlib.util.spec_from_file_location('effective25_gc_window',window_path)
        window=importlib.util.module_from_spec(definition)
        definition.loader.exec_module(window)
        sys.modules['effective25_gc_window']=window
    elif Path(window.__file__).resolve()!=window_path:
        raise RuntimeError('mixed original GC window module in video child')
    if __package__:from .video_split_state import Consumer,RemoteModel
    else:from video_split_state import Consumer,RemoteModel
    record('python_video_imports_end');check()
    record('original_driver_api_begin')
    api=load_api()  # Original board/version/five-driver SHA checks; once in child.
    record('original_driver_api_end');check()
    return N(Hardware=Hardware,validate_description=validate_description,HybridResources=HybridResources,
        ShadowFusion=ShadowFusion,DashboardModel=DashboardModel,make_video_class=make_video_class,
        Window=window.Window,Consumer=Consumer,RemoteModel=RemoteModel,api=api)


def verify_driver_sources(api):
    """Recheck loaded driver's original identity after binding; do not reload API."""
    from joint_video_guard import DRIVER_HASHES
    import pynq
    if pynq.__version__!='3.1.1' or set(api.driver_identity)!=set(DRIVER_HASHES):
        raise RuntimeError('preloaded video driver identity differs')
    for name,digest in DRIVER_HASHES.items():
        identity=api.driver_identity[name]
        module=sys.modules.get('pynq.lib.video.'+name[:-3])
        path=Path(identity['path'])
        if (module is None or Path(module.__file__).resolve()!=path.resolve()
                or identity['sha256']!=digest or hashlib.sha256(path.read_bytes()).hexdigest()!=digest):
            raise RuntimeError('preloaded video driver source changed: '+name)


def typed_cancel(stop):
    if stop.is_set():
        if __package__:from .joint_video_transport import UserStop
        else:from joint_video_transport import UserStop
        raise UserStop('user stop requested')
    return False


class ArmCamera:
    def __init__(self,camera,manager):self.original,self.manager=camera,manager
    def __getattr__(self,name):return getattr(self.original,name)
    def _arm(self):
        m=self.manager;epoch=m.control.epoch.value
        if epoch and m.loop.started_ns is None:
            m.window.enter()  # Same original cyclic-GC window, now in its own process.
            m.video.arm(epoch);m.loop.arm(epoch)
    def grab(self):
        self._arm();result=self.original.grab();self._arm();return result


class BorrowedOwner:
    """No configuration/reset/unlock authority in the video process."""
    def __init__(self,hardware,identity):
        self._hardware,self.identity=hardware,identity;self.state='bound'
        self._io={name:hardware.mmio(name) for name in VIDEO_PORTS}
    def open(self):
        if not self._hardware.is_loaded():raise RuntimeError('borrowed integrated Overlay is no longer current')
        return self.identity
    def close(self):raise RuntimeError('child cannot close/reset global owner')
    def release_after_buffers(self,**kwargs):raise RuntimeError('child cannot release global lease')


class VideoResources:
    def __init__(self,spec,channel,control,*,dependencies=None):
        self.spec,self.channel,self.control=spec,channel,control
        self.dependencies=dependencies;self.hardware=None
        self.video=self.loop=self.window=self.consumer=self.model=self.fusion=None
        self.camera_cleanup=None;self.reference=None;self.identity=None
        self.expected_stop_cancellation=False;self.cancellation_observed_ns=None
    def record_resource_event(self,event):
        if not self.control.prepared.is_set():
            self.control.record_startup('resource:'+event['stage'])
            self.check_startup()
    def check_startup(self):
        if __package__:from .video_split_process import check_child_startup
        else:from video_split_process import check_child_startup
        check_child_startup(self.spec,self.control)
    def prepare(self):
        # run_child has already validated the full new manifest.
        self.check_startup()
        d=self.dependencies
        if d is None:d=load_dependencies(root=self.spec['root'],check=self.check_startup,record=self.control.record_startup)
        self.control.record_startup('bound_driver_recheck_begin')
        verify_driver_sources(d.api)
        self.control.record_startup('bound_driver_recheck_end');self.check_startup()
        self.model,self.fusion,self.window=d.DashboardModel(),d.ShadowFusion(),d.Window()
        self.consumer=d.Consumer(self.channel,self.model,self.fusion)
        manager=self
        class ChildResources(d.HybridResources):
            def process_ready_frame(self,*a,**k):
                manager.consumer.sync()
                return super().process_ready_frame(*a,**k)
            def close(self):raise RuntimeError('use coordinated child release after physical DMA halt')
        self.control.record_startup('borrowed_overlay_begin');self.check_startup()
        self.hardware=hardware=d.Hardware(Path(self.spec['root'])/'hardware/heart_v3b25_main.bit')
        self.control.record_startup('borrowed_overlay_end');self.check_startup()
        d.validate_description(hardware.description)
        if not hardware.is_loaded():raise RuntimeError('parent bit is not current in video child')
        self.check_startup();self.control.record_startup('borrowed_ports_begin')
        owner=BorrowedOwner(hardware,self.spec['owner_identity'])
        if ((owner._io['vision_0'].read(0),owner._io['vision_0'].read(4),owner._io['vision_0'].read(0x18))
                !=(0x56334232,0x20000,self.spec['vision_epoch'])):
            raise RuntimeError('child spatial silicon/run epoch mismatch')
        self.control.record_startup('borrowed_ports_end');self.check_startup()
        self.video=ChildResources(Path(self.spec['root']),owner=owner,identity=self.spec['owner_identity'],api=d.api,
            cancelled=lambda:typed_cancel(self.control.stop),
            on_event=self.record_resource_event,
            model=d.RemoteModel(self.consumer),fusion=self.fusion)
        self.check_startup()
        self.identity=self.video.open()
        self.check_startup()
        self.loop=d.make_video_class()(self.video,Path(self.spec['output']))
        self.loop._stop=self.control.stop;self.loop._ready=self.control.loop_ready
        self.video.camera=ArmCamera(self.video.camera,self)
        return dict(self.identity,video_process_pid=__import__('os').getpid(),bitstream_downloaded_by_child=False,
                    camera_started=True,hdmi_started=True,video_port_names=list(VIDEO_PORTS),
                    preparation_submissions=self.video.preparation_submissions)
    def run(self):
        self.loop.run()
        fault=self.loop.fault
        if fault:
            request=self.control.stop_requested_ns.value
            observed=time.monotonic_ns()
            if fault.get('type')=='UserStop' and self.control.stop.is_set() and 0<request<=observed:
                self.expected_stop_cancellation=True;self.cancellation_observed_ns=observed
            else:raise RuntimeError(fault['message'])
    def close_camera(self):
        if self.camera_cleanup is not None:return self.camera_cleanup
        if self.window is not None:self.window.restore('video_writer_drained_before_finalization')
        video=self.video
        if video is not None and video.camera is not None:video.camera.release()
        self.camera_cleanup=dict(camera_released=True)
        return self.camera_cleanup
    def release(self,proof):
        # run_child validated the actual three-DMA+heart stop result and context.
        if __package__:from .video_split_process import physical_halted
        else:from video_split_process import physical_halted
        if ((proof.get('run_epoch'),proof.get('manifest_sha256'))!=
                (self.spec['run_epoch'],self.spec['manifest_sha256']) or not physical_halted(proof.get('joint',{}))):
            raise RuntimeError('physical stop proof missing; no HDMI/CMA release')
        video=self.video
        if video is None:return dict(cleanup_complete=True,buffers_released=True,hdmi_closed=True)
        if video.hdmi is not None:
            with video.guard.budget(3,'close',allow_halted_errors=True):video.hdmi.close()
        if video.port is not None:video.port.active_destination=None
        if video.pending is not None:video.pending.freebuffer();video.pending=None
        if video.input is not None:video.input.freebuffer();video.input=None
        if video.vdma is not None:
            frames=video.vdma.writechannel._frames
            with video.guard.budget(2,'release stopped frame cache',allow_halted_errors=True):
                for i in range(len(frames)):frames[i]=None
            video.vdma.writechannel._cache.clear()
        video.cleanup=dict(cleanup_complete=True,buffers_released=True,hdmi_closed=True,
            camera_released=True,global_lease_owned_by_parent=True,physical_dma_halt_proof=proof['joint'])
        if video.retained:
            try:self.reference=video.post_verify()
            except BaseException as exc:self.reference=dict(matched=False,error=dict(type=type(exc).__name__,message=str(exc)))
        return dict(cleanup_complete=True,buffers_released=True,hdmi_closed=True)
    def report(self):
        original=self.loop.report() if self.loop else None
        effective=dict(original) if original else None
        if effective and self.expected_stop_cancellation:
            effective.update(fault=None,stop_reason='stop_requested')
        return dict(video=effective,original_video_fault=original.get('fault') if original else None,
            original_stop_reason=original.get('stop_reason') if original else None,
            expected_stop_cancellation=self.expected_stop_cancellation,
            stop_was_requested=self.control.stop.is_set(),stop_request_ns=self.control.stop_requested_ns.value,
            cancellation_observed_ns=self.cancellation_observed_ns,
            cancelled_inflight_frames=max(0,getattr(self.video,'captured',0)-getattr(self.video,'submitted',0)) if self.expected_stop_cancellation else 0,
            display=self.video.hybrid_report() if self.video else None,
            fusion=self.fusion.report() if self.fusion else None,model=self.model.report() if self.model else None,
            gc_window=self.window.report() if self.window else None,post_verification=self.reference,
            camera_started=self.video is not None and self.video.camera is not None,
            preparation_submissions=self.video.preparation_submissions if self.video else 0)
