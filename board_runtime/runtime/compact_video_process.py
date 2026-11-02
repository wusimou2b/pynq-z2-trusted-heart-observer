"""Explicit video process lifecycle. Stop request is never a DMA halt proof."""
import json
from pathlib import Path
import time
import sys
import threading
import multiprocessing as mp
from dataclasses import dataclass

DMA_NAMES={'vision_dma','display_dma','hdmi_vdma'}
OWNER_PROGRESS_NS=2_000_000_000


class OwnerLost(RuntimeError):
    pass


class SharedJSON:
    def __init__(self,ctx,size=65536):
        self.data=ctx.RawArray('B',size);self.length=ctx.RawValue('I',0);self.lock=ctx.Lock()
    def write(self,value):
        data=json.dumps(value,allow_nan=False,separators=(',',':')).encode('utf-8')
        if len(data)>len(self.data):raise BufferError('bounded video lifecycle report full')
        if not self.lock.acquire(timeout=.05):raise TimeoutError('video lifecycle writer lock50ms')
        try:memoryview(self.data).cast('B')[:len(data)]=data;self.length.value=len(data)
        finally:self.lock.release()
    def read(self):
        if not self.lock.acquire(timeout=.05):raise TimeoutError('video lifecycle reader lock50ms')
        try:data=bytes(memoryview(self.data).cast('B')[:self.length.value])
        finally:self.lock.release()
        return json.loads(data) if data else {}


class Control:
    def __init__(self,ctx):
        for name in ('preloaded','binding_ready','prepared','run','loop_ready','stop','loop_stopped','halted','buffers_done','faulted'):
            setattr(self,name,ctx.Event())
        self.epoch=ctx.Value('q',0)  # ARM32 requires a lock for coherent 64-bit publication.
        self.stop_requested_ns=ctx.Value('q',0)
        self.owner_progress_ns=ctx.Value('q',0)
        self.identity,self.details,self.failure,self.halt_proof=(SharedJSON(ctx) for _ in range(4))
        self.binding,self.preload_info,self.startup=(SharedJSON(ctx) for _ in range(3))
        self._startup_rows=[]
    def record_startup(self,phase,**details):
        if len(self._startup_rows)>=64:raise BufferError('video startup event capacity64 exceeded')
        self._startup_rows.append(dict(phase=phase,at_ns=time.monotonic_ns(),details=details))
        self.startup.write(dict(events=self._startup_rows))


def physical_halted(joint):
    dma=joint.get('dma',{})
    return bool(joint.get('cleanup_complete') is True and set(dma)==DMA_NAMES and
         all(x.get('halted') is True and not x.get('error_bits') and not x.get('error') for x in dma.values()))


def verify_spec(spec):
    if __package__:from .video_split_guard import verify
    else:from video_split_guard import verify
    verify(spec['root'],spec['manifest_sha256'])


def factory(spec,channel,control,*,dependencies=None):
    # Both imports are after the pure manifest check in run_child.
    if __package__:from .video_split_resources import VideoResources
    else:from video_split_resources import VideoResources
    return VideoResources(spec,channel,control,dependencies=dependencies)


def pl_mapping_count(path=Path('/proc/self/maps')):
    count=0
    for line in Path(path).read_text('ascii').splitlines():
        fields=line.split(None,5)
        if len(fields)<6 or fields[5].strip()!='/dev/mem':continue
        lo,hi=(int(x,16) for x in fields[0].split('-'));offset=int(fields[2],16)
        count+=int(offset<0x80000000 and offset+hi-lo>0x40000000)
    return count


@dataclass(frozen=True)
class PreparedVideo:
    # Lives only in the video child: driver classes/API never travel through IPC.
    dependencies: object
    report: dict


def check_child_startup(spec,control):
    if __package__:from .video_split_resources import typed_cancel
    else:from video_split_resources import typed_cancel
    typed_cancel(control.stop)
    if time.monotonic_ns()>=spec.get('startup_deadline_ns',2**63-1):
        raise TimeoutError('startup300s video startup deadline reached')


def preload_dependencies(spec,control):
    # Original driver imports may initialize library/PS state. They are not a
    # no-hardware probe. No Overlay/MMIO/camera/HDMI/CMA objects are constructed.
    if __package__:from .video_split_resources import load_dependencies
    else:from video_split_resources import load_dependencies
    began=time.monotonic_ns()
    check_child_startup(spec,control)
    dependencies=load_dependencies(root=spec['root'],check=lambda:check_child_startup(spec,control),record=control.record_startup)
    check_child_startup(spec,control)
    mappings=pl_mapping_count()
    if mappings:raise RuntimeError('video driver preload unexpectedly retained PL mappings')
    return PreparedVideo(dependencies,dict(driver_api_loaded=True,pynq_imported=True,
        driver_identity=dependencies.api.driver_identity,pl_mapping_count=mappings,
        device_construction_deferred=True,elapsed_ns=time.monotonic_ns()-began))


def retained_run_child(spec,channel,control,make,verify,preloader=None):
    resource=None;details={};stage='identity';switch_before=sys.getswitchinterval();dependencies=None
    watch_done=threading.Event();watch=None;fault_lock=threading.Lock()
    def fault(exc,where=None):
        with fault_lock:
            if not control.faulted.is_set():
                try:control.failure.write(dict(stage=where or stage,type=type(exc).__name__,message=str(exc)[:4096]))
                finally:control.faulted.set()
    def watch_owner():
        parent=mp.parent_process()
        while not watch_done.wait(.05) and not control.stop.is_set():
            reason=None
            if parent is None or not parent.is_alive():reason='physical owner process exited'
            elif not control.owner_progress_ns.get_lock().acquire(timeout=.05):
                reason='owner progress publication lock50ms unavailable'
            else:
                try:stamp=control.owner_progress_ns.value
                finally:control.owner_progress_ns.get_lock().release()
                if stamp and not 0<=time.monotonic_ns()-stamp<=OWNER_PROGRESS_NS:
                    reason='formal owner progress absent for2s'
            if reason:
                # No MMIO, camera.close, process kill, DMA proof or CMA free in
                # this thread. Only the original video loop performs cleanup.
                try:fault(OwnerLost(reason),'owner_liveness')
                finally:control.stop.set()
                return
    try:
        control.record_startup('identity_begin')
        verify(spec)
        control.record_startup('identity_end')
        watch=threading.Thread(target=watch_owner,name='video-owner-liveness',daemon=True)
        watch.start()
        check_child_startup(spec,control)
        sys.setswitchinterval(.001)  # Same scoped video-owner setting as the retained owner.
        construct=True
        if preloader is not None:
            stage='preload';control.record_startup('driver_preload_begin')
            prepared=preloader(spec,control)
            if not isinstance(prepared,PreparedVideo):raise TypeError('video dependency handoff differs')
            dependencies=prepared.dependencies
            control.preload_info.write(prepared.report);control.preloaded.set()
            control.record_startup('driver_preload_end')
            while not control.binding_ready.wait(.02):
                if control.stop.is_set():construct=False;break
                if time.monotonic_ns()>=spec.get('startup_deadline_ns',2**63-1):
                    raise TimeoutError('startup300s video preload binding deadline reached')
            if construct and not control.stop.is_set():
                stage='binding_identity';bound=control.binding.read()
                if (set(bound)!={'run_epoch','manifest_sha256','owner_identity','vision_epoch'}
                        or (bound['run_epoch'],bound['manifest_sha256'])!=(spec['run_epoch'],spec['manifest_sha256'])
                        or type(bound['vision_epoch']) is not int or bound['vision_epoch']<0
                        or not isinstance(bound['owner_identity'],dict)):
                    raise ValueError('preloaded video binding identity differs')
                spec=dict(spec,owner_identity=bound['owner_identity'],vision_epoch=bound['vision_epoch'])
                control.record_startup('bound_identity_begin');verify(spec)
                control.record_startup('bound_identity_end')
            else:construct=False
        if construct:
            check_child_startup(spec,control)
            stage='construct'
            resource=make(spec,channel,control,dependencies=dependencies) if dependencies is not None else make(spec,channel,control)
            stage='prepare';control.record_startup('physical_prepare_begin')
            control.identity.write(resource.prepare());control.prepared.set()
            control.record_startup('physical_prepare_end')
            while not control.run.wait(.02):
                if control.stop.is_set():break
            if not control.stop.is_set():
                stage='video_loop';resource.run()
    except BaseException as exc:fault(exc)
    finally:
        watch_done.set()
        if watch is not None:watch.join()
        if resource is not None:
            try:details.update(resource.close_camera())
            except BaseException as exc:stage='camera_release';fault(exc);details['camera_released']=False
        else:details['camera_released']=True
        failure=control.failure.read() if control.faulted.is_set() else None
        loss=failure if failure and failure.get('type')=='OwnerLost' else None
        details.update(no_resources=resource is None,owner_loss=loss,
                       cleanup_complete=resource is None,buffers_released=resource is None)
        if loss and spec.get('output'):
            # The dead parent cannot export shared state. Preserve a small
            # child-owned receipt after capture stops, without claiming DMA halt.
            try:
                target=Path(spec['output'])/'owner-loss.json';target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('x',encoding='utf-8') as sink:
                    json.dump(dict(run_epoch=spec['run_epoch'],manifest_sha256=spec['manifest_sha256'],
                        video_pid=__import__('os').getpid(),at_ns=time.monotonic_ns(),fault=loss,
                        camera_released=details.get('camera_released') is True,
                        dma_halt_proven=False,buffers_released=False,cleanup_complete=False),sink,indent=2)
                details['owner_loss_file']=str(target)
            except Exception as exc:details['owner_loss_export_error']=dict(type=type(exc).__name__,message=str(exc))
        control.details.write(details)
        control.loop_stopped.set();control.prepared.set();control.loop_ready.set()
    if resource is None:
        sys.setswitchinterval(switch_before)
        details.update(cleanup_complete=True,buffers_released=True,no_resources=True)
        control.details.write(details);control.buffers_done.set();return
    # The child keeps all MMIO/CMA references while awaiting physical stop.
    control.halted.wait()
    try:
        proof=control.halt_proof.read()
        if (proof.get('run_epoch'),proof.get('manifest_sha256'))!=(spec['run_epoch'],spec['manifest_sha256']):
            raise ValueError('DMA halt proof identity differs')
        if not physical_halted(proof.get('joint',{})):raise RuntimeError('three DMA halt proof absent')
        if details.get('camera_released') is not True:raise RuntimeError('camera release unconfirmed; retain buffers')
        stage='buffers_release';details.update(resource.release(proof))
        details.update(resource.report())
        if details.get('cleanup_complete') is not True or details.get('buffers_released') is not True:
            raise RuntimeError('video buffers release unconfirmed')
    except BaseException as exc:
        fault(exc);details.update(cleanup_complete=False,buffers_released=False)
    control.details.write(details);control.buffers_done.set()
    if not details.get('cleanup_complete'):
        # Never exit and implicitly free active/uncertain CMA. Only an external
        # explicit recovery/reboot can end this quarantined hardware owner.
        threading.Event().wait()
    sys.setswitchinterval(switch_before)


class ProcessVideo:
    def __init__(self,ctx,spec,channel,*,factory=factory,verify=verify_spec,parent_stop=None):
        self.ctx,self.spec,self.channel=ctx,dict(spec),channel
        self.control=Control(ctx);self.make,self.verify=factory,verify
        self.process=None;self.parent_stop=parent_stop;self.cleanup=None
        self._joint=None;self._attempted=False
        self._preloading=False;self._bound=False;self._prepare_called=False
    @property
    def fault(self):
        return (self.control.failure.read() or dict(stage='lifecycle_report',message='video fault report unavailable')) if self.control.faulted.is_set() else None
    def is_alive(self):return bool(self.process and self.process.is_alive())
    def _check_startup(self):
        if self.parent_stop is not None and self.parent_stop.is_set():
            self.request_stop();raise RuntimeError('parent startup cancelled; no retry')
        if self.control.stop.is_set():raise RuntimeError('video startup cancelled')
        if time.monotonic_ns()>=self.spec.get('startup_deadline_ns',2**63-1):
            self.request_stop();raise TimeoutError('startup300s startup deadline reached')
    def preload(self,*,preloader=preload_dependencies):
        if self._attempted:raise RuntimeError('video process already attempted; no retry')
        self._attempted=True;self._check_startup()
        self._preloading=True
        self.process=self.ctx.Process(target=run_child,args=(self.spec,self.channel,self.control,self.make,self.verify,preloader),
            name='joint25-camera-spatial-hdmi-owner',daemon=False)
        self.process.start()
    def bind_owner(self,identity,vision_epoch):
        if not self._preloading or self._bound:raise RuntimeError('video preload not available or already bound')
        self._check_startup()
        if self.fault:raise RuntimeError('video preload failed: '+self.fault['message'])
        self.control.binding.write(dict(run_epoch=self.spec['run_epoch'],manifest_sha256=self.spec['manifest_sha256'],
            owner_identity=identity,vision_epoch=vision_epoch))
        self._bound=True;self.control.binding_ready.set()
    def close_preload(self):
        if self._bound:raise RuntimeError('bound video requires physical DMA stop proof')
        self.request_stop()
        if self.process is None or self.process.pid is None:
            # No binding was published; preserve the original spawn error.
            # An absent PID is not proof of a natural process exit.
            return dict(no_resources=True,hardware_never_bound=True,process_start_confirmed=False,
                cleanup_complete=False,process_exit_confirmed=False)
        while not self.control.loop_stopped.wait(.1):
            if not self.is_alive():raise RuntimeError('preload exited without stopped acknowledgement')
        detail=self.control.details.read()
        if not self.control.buffers_done.wait(.1):
            while self.is_alive() and not self.control.buffers_done.wait(.1):pass
        detail=self.control.details.read()
        if not detail.get('no_resources') or not detail.get('cleanup_complete') or not detail.get('buffers_released'):
            raise RuntimeError('unbound video preload resource state unknown; retain')
        while not self.join(.1):pass
        if self.process.exitcode!=0:raise RuntimeError('unbound video preload abnormal exit')
        return dict(detail,process_exitcode=0,process_exited=True)
    def prepare(self):
        if self._prepare_called:raise RuntimeError('video process already attempted; no retry')
        self._prepare_called=True;self._check_startup()
        if self._preloading:
            if not self._bound:raise RuntimeError('preloaded video requires parent binding before prepare')
        else:
            if self._attempted:raise RuntimeError('video process already attempted; no retry')
            self._attempted=True
            self.process=self.ctx.Process(target=run_child,args=(self.spec,self.channel,self.control,self.make,self.verify),
                name='joint25-camera-spatial-hdmi-owner',daemon=False)
            self.process.start()
        while not self.control.prepared.wait(.02):
            self._check_startup()
            if not self.is_alive():raise RuntimeError('video process exited during preparation')
        if self.fault:raise RuntimeError('video preparation failed: '+self.fault['message'])
        self._check_startup();return self.control.identity.read()
    def start(self):
        if not self.control.prepared.is_set() or self.control.run.is_set() or self.control.stop.is_set():
            raise RuntimeError('video not prepared or already started/stopped')
        self.control.run.set()
        if not self.control.loop_ready.wait(3.):
            self.request_stop();raise TimeoutError('original video loop ready3s exceeded')
        if self.fault:raise RuntimeError('video loop failed: '+self.fault['message'])
    def arm(self,epoch):
        if type(epoch) is not int or epoch<=0:raise ValueError('invalid heart epoch')
        if self.control.epoch.value or self.control.stop.is_set():raise RuntimeError('video already armed/stopped')
        self.heartbeat()
        self.control.epoch.value=epoch
    def heartbeat(self):
        # The owner's running loop, not a timer thread or a fresh BPM, proves
        # progress. This also detects a crashed owner while Linux dumps core.
        if not self.control.owner_progress_ns.get_lock().acquire(timeout=.05):
            raise TimeoutError('owner progress writer lock50ms')
        try:self.control.owner_progress_ns.value=time.monotonic_ns()
        finally:self.control.owner_progress_ns.get_lock().release()
    def request_stop(self):
        with self.control.stop_requested_ns.get_lock():
            if not self.control.stop_requested_ns.value:self.control.stop_requested_ns.value=time.monotonic_ns()
        self.control.stop.set()
    def wait_loop_stopped(self,timeout):return self.control.loop_stopped.wait(timeout)
    def join(self,timeout):
        if self.process is not None:self.process.join(timeout)
        return not self.is_alive()
    def release(self,owner):
        if self.cleanup is not None:return self.cleanup
        if not self.control.loop_stopped.is_set():raise RuntimeError('video loop/native call still active; retain DMA')
        if self._joint is None:self._joint=owner.close()
        if not physical_halted(self._joint):raise RuntimeError('three DMA/heart halt not confirmed; preserve buffers/lease')
        if not self.control.halted.is_set():
            self.control.halt_proof.write(dict(run_epoch=self.spec['run_epoch'],
                manifest_sha256=self.spec['manifest_sha256'],joint=self._joint))
            self.control.halted.set()
        notice=time.monotonic()
        while not self.control.buffers_done.wait(.1):
            if not self.is_alive():raise RuntimeError('video exited without buffers acknowledgement; preserve lease')
            if time.monotonic()-notice>=5:
                print('等待视频进程关闭HDMI/释放CMA；保留租约，不强杀。',flush=True);notice=time.monotonic()
        detail=self.control.details.read()
        if detail.get('cleanup_complete') is not True or detail.get('buffers_released') is not True:
            raise RuntimeError('video buffer cleanup failed; preserve child and lease')
        while not self.join(.1):
            if time.monotonic()-notice>=5:
                print('视频缓冲已释放，等待进程自然退出后再解锁。',flush=True);notice=time.monotonic()
        if self.process.exitcode!=0:raise RuntimeError('video process abnormal exit; retain global lease')
        owner.release_after_buffers(buffers_released=True)
        self.cleanup=dict(detail,joint=self._joint,cleanup_complete=True,actual_lease_released=True,
                          process_exited=True,process_exitcode=self.process.exitcode)
        return self.cleanup
    def report(self):
        details=self.control.details.read()
        video=details.get('video') or dict(metrics={},fault=self.fault,thread_exited=self.control.loop_stopped.is_set())
        return dict(video,resource_details=details,process_alive=self.is_alive(),
            preload=self.control.preload_info.read(),startup=self.control.startup.read(),
            loop_stopped=self.control.loop_stopped.is_set(),buffers_done=self.control.buffers_done.is_set(),
            process_exitcode=self.process.exitcode if self.process else None,fault=self.fault)

from compact_delivery_runtime import video_child as run_child
