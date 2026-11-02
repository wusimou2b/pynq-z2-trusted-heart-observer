"""Keep frozen heart preparation; attach video and defer the final shared lease."""
from pathlib import Path
import time

if __package__:
    from .joint_heart_binding import JointBinding,HeartOwner
    from .joint_video_runtime import load_board_api,DeferredLease,describe
    from .joint_video_pack import packing_preflight
    from .joint_shared_video import SharedVideoResources
    from .joint_video_five import VideoFive
else:
    from joint_heart_binding import JointBinding,HeartOwner
    from joint_video_runtime import load_board_api,DeferredLease,describe
    from joint_video_pack import packing_preflight
    from joint_shared_video import SharedVideoResources
    from joint_video_five import VideoFive


class ConcurrentBinding(JointBinding):
    def __init__(self,root,*,frozen_root=None,api_factory=load_board_api,owner_factory=HeartOwner,loop_factory=VideoFive):
        self.api_factory,self.owner_factory,self.loop_factory=api_factory,owner_factory,loop_factory
        self.api=self.preflight=self.deferred_lease=None
        self.video=self.video_runner=self.video_identity=self.video_cleanup=None
        self.quarantine_required=False;self._attempted=False
        def make_owner(directory):return self.owner_factory(directory,lease=self.deferred_lease)
        super().__init__(root,frozen_root=frozen_root,owner_factory=make_owner)

    def prepare(self,base,output,*,hardware=False):
        if hardware is not True:raise ValueError('concurrent preparation requires explicit hardware=True')
        if self._attempted:raise RuntimeError('concurrent preparation already attempted')
        self._attempted=True
        try:
            # Driver registration and actual native-copy check precede the one download.
            self.api=self.api_factory();self.preflight=packing_preflight(self.api.cv2)
            self.deferred_lease=DeferredLease(self.api.lease_factory())
            session=super().prepare(base,output,hardware=True)
        except BaseException as exc:
            self.prepare_error=self.prepare_error or describe(exc,'concurrent_prepare')
            raise
        try:
            directory=Path(output).parent/'video';directory.mkdir(parents=True,exist_ok=False)
            self.video=SharedVideoResources(self.root,owner=self.owner,identity=self.identity,api=self.api,
                lease=self.deferred_lease,preflight=self.preflight,cancelled=lambda:False,on_event=lambda e:None)
            self.video_identity=self.video.open()
            self.video_runner=self.loop_factory(self.video,directory)
            original_begin=session.source.begin
            def begin():
                result=original_begin()
                self.video_runner.arm(result['started_ns'])
                return result
            session.source.begin=begin
            original_stop=session.stop
            def stop(*args,**kwargs):
                # Frozen start() also calls self.stop() on startup failure.
                # Intercept that path before its GC/finalization/release hooks.
                self.video_runner.request_stop();notice=time.monotonic()
                while not self.video_runner.join(.1):
                    if time.monotonic()-notice>=5:
                        try:print('等待视频线程停止；保留共享所有者、CMA和锁，不强杀。',flush=True)
                        except BaseException:pass
                        notice=time.monotonic()
                return original_stop(*args,**kwargs)
            session.stop=stop
            session._preflight.update(concurrent_video_target_fps=5,concurrent_display_mode='notebook_heart_hdmi_vision',
                video_shares_existing_owner=True)
            return session
        except BaseException as exc:
            self.prepare_error=describe(exc,'concurrent_video_prepare')
            try:session._release_owner()
            except BaseException as release_error:self.release_error=describe(release_error,'concurrent_prepare_release')
            raise

    def release(self):
        if self.video_runner is not None and self.video_runner.is_alive():
            self.quarantine_required=True
            raise RuntimeError('video thread still active; do not close shared owner or release buffers')
        if self.video is not None:
            self.video_cleanup=self.video.close()
            self.cleanup=dict(self.video_cleanup.get('joint') or {})
            self.cleanup['cleanup_complete']=self.video_cleanup['cleanup_complete']
            self.quarantine_required=self.video_cleanup['quarantine_required']
        else:
            self.cleanup=self.owner.close() if self.owner is not None else dict(cleanup_complete=True,download_attempts=0,dma={})
            safe=self.cleanup.get('cleanup_complete') and (not self.cleanup.get('download_attempts') or
                len(self.cleanup.get('dma',{}))==2 and all(v.get('halted') for v in self.cleanup['dma'].values()))
            if safe and self.deferred_lease is not None:self.deferred_lease.finish()
            self.quarantine_required=bool(self.deferred_lease and self.deferred_lease.held)
        if not self.cleanup['cleanup_complete']:
            raise RuntimeError('joint concurrent cleanup not confirmed; preserve results, no retry')

    def report(self):
        result=super().report()
        result.update(camera_started=bool(self.video and self.video.camera is not None),
            hdmi_started=bool(self.video and self.video.hdmi is not None),
            vision_frame_transferred=bool(self.video and self.video.port and self.video.port.completed),
            video_cleanup=self.video_cleanup,video_identity=self.video_identity,
            quarantine_required=self.quarantine_required,
            actual_lease_released=not bool(self.deferred_lease and self.deferred_lease.held))
        return result
