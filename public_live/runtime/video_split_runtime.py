"""Scoped new video process boundary around the preserved journal60 owner."""
from contextlib import ExitStack,contextmanager
from functools import partial
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import time
import uuid
from types import SimpleNamespace as N

if __package__:
    from .video_split_guard import startup_deadline_ns
    from .video_split_process import ProcessVideo,physical_halted
    from .video_split_state import StateChannel
else:
    from video_split_guard import startup_deadline_ns
    from video_split_process import ProcessVideo,physical_halted
    from video_split_state import StateChannel


class VideoProxy:
    """Parent report view only. Every physical buffer remains in the child."""
    def __init__(self,runner):self.runner=runner;self._armed=None
    @property
    def buffer(self):
        released=self.runner.control.buffers_done.is_set() and self.runner.control.details.read().get('buffers_released') is True
        return None if released else True
    @property
    def pending(self):return self.buffer
    @property
    def camera(self):return True if self.runner.control.identity.read().get('camera_started') else None
    @property
    def hdmi(self):return True if self.runner.control.identity.read().get('hdmi_started') else None
    @property
    def port(self):return N(completed=(self.runner.report().get('metrics')or{}).get('completed_frames',0))
    @property
    def preparation_submissions(self):return self.runner.control.identity.read().get('preparation_submissions',0)
    def arm(self,epoch):
        if self._armed is not None:raise RuntimeError('video resources already armed')
        self._armed=epoch  # ShadowBinding's next call arms both resources+loop in the child.
    def hybrid_report(self):return self.runner.control.details.read().get('display')
    def post_verify(self):return self.runner.control.details.read().get('post_verification') or dict(attempted=False,matched=False)


def assess_startup_cleanup(summary,owner,*,delegate,directory,**kwargs):
    """Confirm release after pre-session failure without fabricating a session."""
    result=delegate(summary,owner,**kwargs)
    if summary or result.get('resources_released'):return result
    directory=Path(directory)
    try:
        load=lambda n:json.loads((directory/n).read_bytes())
        inherited,trace,early=(load(n) for n in ('owner_result.json','owner_startup.json','early-ps-owner.json'))
        raw=(directory/'startup_events.jsonl').read_bytes()
        events=[json.loads(line) for line in raw.splitlines()]
        video=owner.get('video') or {};cleanup=owner.get('cleanup') or {};ps=early.get('final_info') or {}
        released=bool(kwargs.get('parent_error') is not None and kwargs.get('owner_exitcode')==0
            and inherited.get('summary') is None and inherited.get('error') is not None
            and inherited.get('video_process_exited') is True and owner.get('prepare_error') is not None
            and owner.get('inputs_unchanged') is True and owner.get('identity_error') is None
            and owner.get('retention_reasons')==[] and owner.get('quarantine_required') is False
            and owner.get('actual_lease_released') is True and cleanup.get('actual_lease_released') is True
            and trace.get('trace_closed') is True and not trace.get('unpaired_begins')
            and hashlib.sha256(raw).hexdigest()==trace.get('events_sha256')
            and not any(e.get('phase') in ('formal_epoch','source_begin','heart_start') for e in events)
            and not any((directory/'capture'/n).exists() for n in ('raw.csv','results.csv','summary.json'))
            and physical_halted(cleanup) and (cleanup.get('main_heart') or {}).get('quiescent') is True
            and (owner.get('video_cleanup') or {}).get('cleanup_complete') is True
            and video.get('process_exitcode')==0 and video.get('process_alive') is False
            and (video.get('cleanup') or {}).get('camera_released') is True
            and (video.get('cleanup') or {}).get('buffers_released') is True
            and (video.get('cleanup') or {}).get('hdmi_closed') is True
            and (video.get('metrics') or {}).get('completed_frames',0)==0
            and early.get('handoffs')==0 and early.get('cleanup_error') is None
            and type(ps.get('exitcode')) is int and ps.get('cleanup_complete') is True
            and ps.get('completed_steps')==ps.get('pl_requests')==0)
        result['startup_cleanup']=dict(proven=released,ps_exitcode=ps.get('exitcode'),
            ps_forced_termination=ps.get('forced_termination'),original_session_summary_missing=True)
        if released:
            result.update(resources_released=True,startup_failure_cleanup_only=True,manual_session_passed=False)
            result['checks']['resources_released']=True
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result['startup_cleanup']=dict(proven=False,error=dict(type=type(exc).__name__,message=str(exc)))
    return result


def checked_download(hardware,*,delegate):
    # PYNQ is already required by this hardware's constructor. Read video
    # sources directly; do not import the unused parent camera/HDMI API.
    import pynq
    from joint_video_guard import DRIVER_HASHES
    if pynq.__version__!='3.1.1':raise RuntimeError('joint video entry requires reviewed PYNQ3.1.1')
    folder=Path(pynq.__file__).resolve().parent/'lib/video'
    for name,digest in DRIVER_HASHES.items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('installed video source changed; no bitstream download: '+name)
    return delegate(hardware)


@contextmanager
def early_digest_prefix(directory,*,worker_entry_ns=None):
    """Move the retained exact-byte reuse earlier; keep its original end barrier."""
    import startup_digest_runtime as original,joint_startup_worker as startup
    from joint_startup import replace_attribute
    scope=original.prefix_digest_scope
    @contextmanager
    def already_active(*args,**kwargs):yield None
    with scope(startup,directory,worker_entry_ns=worker_entry_ns), \
            replace_attribute(original,'prefix_digest_scope',already_active):
        yield


def owner_main(binding,root,directory,mailbox,stop,metrics_ready,*,dependencies=None,sleep=time.sleep,emit=print):
    # Same original loop/heartbeat/Session.stop. Only the video stop barrier is
    # now explicitly loop_stopped, while the child remains alive owning CMA.
    import joint_concurrent_owner as original
    import os,sys
    d=dependencies or original._dependencies();directory=Path(directory);session=None
    result=dict(owner_pid=os.getpid(),parent_pid=os.getppid(),summary=None,error=None,cleanup_complete=False,
        hardware_imported=False,backend_fault='',transport=None,video_thread_joined=False,
        video_loop_stopped=False,video_process_exited=False,video_join_seconds=None)
    try:
        context,cached=d.bootstrap(root,algorithm=True)
        session=d.prepare(Path(root)/'deps/static/checked/base',directory/'capture',hardware=True)
        session._assess_summary=d.assess
        session._preflight.update(owner_process_pid=os.getpid(),display_process_pid=os.getppid(),
            owner_manifest_sha256=context['owner_manifest_sha256'],effective_manifest_sha256=context['effective_manifest_sha256'])
        binding.video_runner.start()
        if stop.is_set():session._request_stop('display_stopped_before_start')
        else:session.start()
        while not stop.is_set():
            snap=session.snapshot();mailbox.publish(snap)
            if binding.video_runner.fault:raise RuntimeError('joint video failed: '+binding.video_runner.fault['message'])
            if snap.state!='running':break
            if not 0<=mailbox.parent_age()<=2_000_000_000:
                raise TimeoutError('Notebook无进展超过2秒，停止联合试验；不自动恢复')
            sleep(.01)
    except BaseException as exc:
        result['error']=original.error(exc,'concurrent_owner')
        if session is not None:session._fail('display_owner',str(exc) or type(exc).__name__)
    finally:
        if session is not None:session._request_stop('display_finished')
        runner=binding.video_runner
        if runner is not None:
            runner.request_stop();began=notice=time.monotonic()
            while not runner.wait_loop_stopped(.1):
                if time.monotonic()-notice>=5:
                    emit('等待视频调用返回；保留DMA/CMA/租约，不强杀。',flush=True);notice=time.monotonic()
            result.update(video_loop_stopped=True,video_join_seconds=time.monotonic()-began)
            if runner.fault and session is not None:
                result['error']=result['error'] or dict({'stage':'video_process'},**runner.fault)
                session._fail('joint_video',runner.fault['message'])
        if session is not None:
            try:mailbox.publish(session.snapshot())
            except BaseException as exc:result['error']=result['error'] or original.error(exc,'transport_finish')
            metrics=None
            if metrics_ready.wait(5.):
                try:metrics=json.loads((directory/'display_metrics.json').read_text('utf-8'))
                except Exception as exc:result['error']=result['error'] or original.error(exc,'display_metrics')
            else:result['error']=result['error'] or original.error(TimeoutError('未收到显示结束审计'),'display_metrics')
            try:
                result['summary'],cleanup_error=d.stop(session,metrics)
                result['error']=result['error'] or cleanup_error
                result['cleanup_complete']=bool(result['summary']['cleanup_complete'] and (binding.video_cleanup or {}).get('cleanup_complete'))
                result['backend_fault']=getattr(session.backend,'_fault','')
            except BaseException as exc:result['error']=result['error'] or original.error(exc,'owner_cleanup')
        result['video_process_exited']=bool(runner and runner.process and not runner.is_alive())
        result['video_thread_joined']=result['video_process_exited']
        result['hardware_imported']=any(n=='pynq' or n.startswith('pynq.') for n in sys.modules)
        result['transport']=mailbox.stats();d.write_new(directory/'owner_result.json',result)


@contextmanager
def install(root,manifest_sha256,parent_stop,*,directory=None):
    import yuyv_joint_binding as base,joint_heart_binding as heart,hybrid_display,joint_concurrent_owner as flow
    import main_spatial_owner as board
    from joint_startup import replace_attribute
    ctx=mp.get_context('spawn');epoch=uuid.uuid4().hex;channel=StateChannel(ctx,epoch,manifest_sha256)
    old_publish=hybrid_display.HybridMailbox.publish
    instances=[];warm=None
    deadline=startup_deadline_ns(time.monotonic_ns())
    def publish(self,snapshot):
        result=old_publish(self,snapshot)
        # This is HybridMailbox's ORIGINAL pre-transport publication stamp.
        # A delayed transfer must not renew the status freshness clock.
        imu=self.fusion.imu
        with imu._lock:
            observed=imu._last['observed_ns'] if imu._last is not None else self.model._published
        channel.publish(snapshot,published_ns=self.model._published,imu_observed_ns=observed)
        return result
    def prepare(self,source,output,*,hardware=False):
        if hardware is not True or self._attempted:raise RuntimeError('single explicit video process attempt required')
        # The frozen YuyvJointBinding.__init__ owner's closure still consumes
        # self.api.lease_factory. Keep that exact board lock, without loading
        # the parent's unused camera/HDMI API or creating a second lease.
        from joint_owner import BoardLease
        self._attempted=True;self.api=N(lease_factory=BoardLease)
        if warm is not None:
            warm._check_startup()
            if warm.fault:raise RuntimeError('video driver preload failed: '+warm.fault['message'])
        pair=base.verify_pair(self.root)['files']
        hashes={'heart_v3b25.bit':pair['heart_v3b25_yuyv.bit'],'heart_v3b25.hwh':pair['heart_v3b25_yuyv.hwh']}
        with replace_attribute(heart,'PAIR_HASHES',hashes):
            session=super(base.YuyvJointBinding,self).prepare(source,output,hardware=True)
        try:
            video_directory=Path(output).parent/'video'
            if warm is None:
                video_directory.mkdir(parents=True,exist_ok=False)
                spec=dict(root=str(root),output=str(video_directory),run_epoch=epoch,manifest_sha256=manifest_sha256,
                    owner_identity=self.identity,vision_epoch=int(self.owner._io['vision_0'].read(0x18)),
                    startup_deadline_ns=deadline)
                runner=ProcessVideo(ctx,spec,channel,parent_stop=parent_stop)
            else:
                if Path(warm.spec['output']).resolve()!=video_directory.resolve():raise ValueError('preloaded video output differs')
                runner=warm
            self.video_runner=runner;self.video=VideoProxy(runner);instances.append(self)
            if warm is not None:runner.bind_owner(self.identity,int(self.owner._io['vision_0'].read(0x18)))
            self.video_identity=runner.prepare()
            original_begin=session.source.begin
            def begin():
                value=original_begin();runner.arm(value['started_ns']);return value
            session.source.begin=begin
            session._preflight.update(concurrent_video_target_fps=5,video_separate_process=True,
                global_overlay_owner='heart_parent',camera_dma_hdmi_owner='video_child',
                image_ipc=False,original_iic_algorithm_and_protections=True)
            return session
        except BaseException as exc:
            self.prepare_error=dict(type=type(exc).__name__,message=str(exc))
            if self.video_runner is not None:
                if self.video_runner.process is None:
                    self.video_runner=self.video=None
                else:
                    self.video_runner.request_stop()
                    while not self.video_runner.wait_loop_stopped(.1):pass
            try:session._release_owner()
            except BaseException as close_error:self.release_error=dict(type=type(close_error).__name__,message=str(close_error))
            raise
    def release(self):
        session=self.session
        callers=list(getattr(session,'_threads',())) if session is not None else []
        callers += [getattr(session,'_finalizer',None),getattr(getattr(session,'_process_chain',None),'_worker',None)]
        if any(p is not None and p.is_alive() for p in callers):
            self.quarantine_required=True;raise RuntimeError('heart callers active; retain global DMA/lease')
        try:
            if self.video_runner is None:
                self.cleanup=self.owner.close() if self.owner else dict(cleanup_complete=True,download_attempts=0,dma={})
                if self.owner and self.cleanup['cleanup_complete']:self.owner.release_after_buffers(buffers_released=True)
                self.video_cleanup=dict(self.cleanup)
            else:
                self.video_cleanup=self.video_runner.release(self.owner)
                self.cleanup=dict(self.video_cleanup['joint'],cleanup_complete=self.video_cleanup['cleanup_complete'])
            self.quarantine_required=bool(not self.cleanup['cleanup_complete'] or self.deferred_lease and self.deferred_lease.held)
            if self.quarantine_required:raise RuntimeError('global video cleanup incomplete; retain')
        except BaseException:self.quarantine_required=True;raise
    try:
        if directory is not None:
            video_directory=Path(directory)/'video';video_directory.mkdir(parents=True,exist_ok=False)
            warm=ProcessVideo(ctx,dict(root=str(root),output=str(video_directory),run_epoch=epoch,
                manifest_sha256=manifest_sha256,startup_deadline_ns=deadline),channel,parent_stop=parent_stop)
            warm.preload()
        with ExitStack() as stack:
            download=board.Hardware.download
            def download_checked(hardware):return checked_download(hardware,delegate=download)
            stack.enter_context(replace_attribute(board.Hardware,'download',download_checked))
            for obj,name,value in ((base.YuyvJointBinding,'prepare',prepare),(base.YuyvJointBinding,'release',release),
                (hybrid_display.HybridMailbox,'publish',publish),(flow,'owner_main',owner_main)):
                stack.enter_context(replace_attribute(obj,name,value))
            yield instances
    finally:
        if warm is not None:
            unbound_cleanup=warm.close_preload() if not warm._bound else None
            with (Path(directory)/'video-process-preload.json').open('x',encoding='utf-8') as sink:
                json.dump(dict(video=warm.report(),unbound_cleanup=unbound_cleanup,
                    hardware_binding_by_parent_only=True),sink,ensure_ascii=False,allow_nan=False)


def verified_heart_entry(connection,backend_source,*,delegate,root,manifest_sha256,**kwargs):
    if __package__:from .video_split_guard import verify
    else:from video_split_guard import verify
    verify(root,manifest_sha256)
    return delegate(connection,backend_source,root=root,**kwargs)


def worker(*args,root,expected_split_manifest_sha256,**kwargs):
    entered_ns=time.monotonic_ns()
    if __package__:from .video_split_guard import verify
    else:from video_split_guard import verify
    verify(root,expected_split_manifest_sha256)
    import journal60_runtime as original,main_heart_process
    from joint_startup import replace_attribute
    original_bridge=main_heart_process.Bridge
    def bridge(source,target,*,run_id):
        guarded=partial(verified_heart_entry,delegate=target,root=root,manifest_sha256=expected_split_manifest_sha256)
        return original_bridge(source,guarded,run_id=run_id)
    failure=None;instances=[]
    try:
        with early_digest_prefix(args[1],worker_entry_ns=entered_ns), \
                install(Path(root),expected_split_manifest_sha256,args[3],directory=args[1]) as instances, \
                replace_attribute(main_heart_process,'Bridge',bridge):
            return original.worker(*args,root=root,**kwargs)
    except BaseException as exc:failure=dict(type=type(exc).__name__,message=str(exc));raise
    finally:
        directory=Path(args[1])
        report=dict(schema='real_video_process_owner_v1',manifest_sha256=expected_split_manifest_sha256,
            original_error=failure,bindings=len(instances),
            videos=[b.video_runner.report() for b in instances if b.video_runner is not None],
            global_configuration_owner='heart_parent',automatic_retry=False)
        if directory.is_dir():
            with (directory/'video-process-owner.json').open('x',encoding='utf-8') as sink:json.dump(report,sink,ensure_ascii=False)


def start_owner(context,*args,root,expected_split_manifest_sha256,**kwargs):
    process=context.Process(target=partial(worker,root=root,expected_split_manifest_sha256=expected_split_manifest_sha256,**kwargs),
        args=args,name='joint25-video-process-coordinator',daemon=False)
    process.start();return process
