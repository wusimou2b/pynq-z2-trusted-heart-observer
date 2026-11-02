"""One new-pair owner; unchanged native IIC and frozen heart lifecycle."""
from pathlib import Path
from types import SimpleNamespace
import time

if __package__:
    from .yuyv_owner import YuyvOwner, Hardware, verify_pair
    from .yuyv_runtime import Resources, load_api
    from .joint_iic_native import NativeIicTransport
    from .joint_iic_native_build import load_verified
    from .joint_heart_binding import JointBinding
    from .joint_video_five import VideoFive
    from .joint_video_runtime import describe
    from .joint_startup import replace_attribute
else:
    from yuyv_owner import YuyvOwner, Hardware, verify_pair
    from yuyv_runtime import Resources, load_api
    from joint_iic_native import NativeIicTransport
    from joint_iic_native_build import load_verified
    from joint_heart_binding import JointBinding
    from joint_video_five import VideoFive
    from joint_video_runtime import describe
    from joint_startup import replace_attribute


class HeartHardware(Hardware):
    def heart_iic(self):
        if not self.is_loaded(): raise RuntimeError('new joint Overlay changed before IIC binding')
        return self._overlay.axi_iic_0


class YuyvHeartOwner(YuyvOwner):
    def __init__(self, directory, hardware_factory=HeartHardware, lease=None, *, library=None, **kwargs):
        self.library = library if library is not None else load_verified(directory)
        super().__init__(directory, hardware_factory, lease, **kwargs)
        self.iic_transport = None
        self._iic_stopped = self._joint_stopped = None

    def heart_ports(self):
        if self.state != 'bound' or not self._hardware.is_loaded():
            raise RuntimeError('YUYV heart owner is not bound/current')
        if self.iic_transport is None:
            self.iic_transport = NativeIicTransport(self._hardware.heart_iic().mmio,
                library=self.library, current=self._hardware.is_loaded)
        return dict(iic=self.iic_transport, nlms_mmio=self._io['nlms_axi_0'],
                    fifo_mmio=self._hardware.mmio('axi_fifo_mm_s_0'))

    def quiesce_iic(self):
        if self._iic_stopped is None:
            try:
                self._iic_stopped = (self.iic_transport.quiesce() if self.iic_transport is not None
                    else dict(iic_quiesced=True, scope='IIC_not_accessed', stop_attempts=0, error=None))
            except BaseException as exc:
                self._iic_stopped = dict(iic_quiesced=False, error=describe(exc, 'iic_quiesce'))
        return self._iic_stopped

    def close(self):
        if self._joint_stopped is None:
            iic = self.quiesce_iic()
            result = super().close()
            result.update(iic=iic, cleanup_scope='native_iic_three_dma_color_vision_reset',
                cleanup_complete=bool(result['cleanup_complete'] and iic['iic_quiesced'] is True
                    and not result['errors'] and not any(v.get('error_bits') for v in result['dma'].values())))
            result['quarantine_required'] = not result['cleanup_complete']
            self._joint_stopped = result
        return self._joint_stopped


class _JointLabels:
    def __init__(self, cv): self.cv = cv
    def __getattr__(self, name): return getattr(self.cv, name)
    def putText(self, image, text, *args, **kwargs):
        prefix = 'YUYV PL | HEART OFF | seq='
        if text.startswith(prefix): text = 'JOINT PL | HEART: NOTEBOOK | seq=' + text[len(prefix):]
        elif 'HEART OFF' in text: raise RuntimeError('YUYV video label contract changed')
        return self.cv.putText(image, text, *args, **kwargs)


class SharedYuyvResources(Resources):
    """Borrow an already bound owner, preserve its sole retained lease."""
    def __init__(self, directory, *, owner, identity, api, **kwargs):
        self.shared_owner, self.joint_identity = owner, identity
        shared_api = SimpleNamespace(**vars(api)); shared_api.cv2 = _JointLabels(api.cv2)
        super().__init__(directory, api_factory=lambda: shared_api, owner_factory=lambda *a, **k: owner, **kwargs)
        self.owner = owner  # The original startup stage guard must see the shared binding before open().

    @property
    def buffer(self): return self.input  # Original retention guard's buffer name.

    def open(self):
        owner = self.shared_owner
        if owner.state != 'bound' or not owner._hardware.is_loaded():
            raise RuntimeError('shared YUYV video requires current bound owner')
        def borrowed():
            if owner.state != 'bound' or not owner._hardware.is_loaded():
                raise RuntimeError('owner changed before borrowing video')
            return self.joint_identity
        with replace_attribute(owner, 'open', borrowed):
            result = super().open()
        result.update(shared_existing_owner=True, heart_capture_started=False,
            heart_capture_managed_by_frozen_session=True,
            heart_display_scope='Notebook only; HDMI is annotated video',
            reference_mode='two_frames_checked_only_after_hardware_cleanup')
        return result

    def close(self):
        if self.cleanup is not None: return self.cleanup
        owner = self.shared_owner
        result = dict(cleanup_complete=False, camera_released=self.camera is None, hdmi_closed=self.hdmi is None,
            buffers_released=False, actual_lease_released=False, quarantine_required=True, errors=[])
        def attempt(stage, fn):
            try: fn(); return True
            except BaseException as exc: result['errors'].append(describe(exc, stage)); return False
        if self.camera is not None: result['camera_released'] = attempt('camera_release', self.camera.release)
        joint = owner.close(); result['joint'] = joint
        dma = joint.get('dma', {})
        halted = bool(not joint['download_attempts'] or set(dma) == {'vision_dma', 'hdmi_vdma', 'display_dma'}
            and all(v.get('halted') is True and not v.get('error_bits') for v in dma.values()))
        safe = bool(joint['cleanup_complete'] and halted and not joint.get('errors') and result['camera_released'])
        if safe and self.hdmi is not None:
            def close_hdmi():
                with self.guard.budget(3, 'close', allow_halted_errors=True): self.hdmi.close()
            result['hdmi_closed'] = attempt('hdmi_close', close_hdmi)
        if safe and result['hdmi_closed'] and not result['errors']:
            def release():
                if self.port is not None: self.port.active_destination = None
                if self.pending is not None: self.pending.freebuffer(); self.pending = None
                if self.input is not None: self.input.freebuffer(); self.input = None
                if self.vdma is not None:
                    frames = self.vdma.writechannel._frames
                    with self.guard.budget(2, 'release stopped frame cache', allow_halted_errors=True):
                        for i in range(len(frames)): frames[i] = None
                    self.vdma.writechannel._cache.clear()
            result['buffers_released'] = attempt('buffers_release', release)
            if result['buffers_released'] and not result['errors']:
                result['actual_lease_released'] = attempt('actual_lease_release',
                    lambda: owner.release_after_buffers(buffers_released=True))
        result.update(captured_frames=self.captured, submitted_frames=self.submitted,
            vision_completed_frames=self.port.completed if self.port else 0,
            camera_release_returned=result['camera_released'], hdmi_close_returned=result['hdmi_closed'],
            lease_released=result['actual_lease_released'])
        result['cleanup_complete'] = bool(safe and result['hdmi_closed'] and result['buffers_released']
            and result['actual_lease_released'] and not result['errors'])
        result['quarantine_required'] = not result['cleanup_complete']
        self.cleanup = result
        return result

    def post_verify(self):
        result = super().post_verify()
        return dict(result, attempted=True, after_hardware_cleanup=True, sample_count=result['compared_frames'],
            total_frames=self.captured, all_frames_verified=False, images_saved=False)


class YuyvJointBinding(JointBinding):
    def __init__(self, root, *, frozen_root=None, api_factory=load_api, owner_factory=YuyvHeartOwner, loop_factory=VideoFive):
        self.api_factory, self.owner_factory, self.loop_factory = api_factory, owner_factory, loop_factory
        self.api = self.deferred_lease = None
        self.video = self.video_runner = self.video_identity = self.video_cleanup = None
        self.quarantine_required = False; self._attempted = False
        def construct(directory):
            obj = self.owner_factory(directory, lease=self.api.lease_factory())
            self.deferred_lease = obj.retained_lease
            return obj
        super().__init__(root, frozen_root=frozen_root, owner_factory=construct)

    def prepare(self, base, output, *, hardware=False):
        if hardware is not True: raise ValueError('requires explicit hardware=True')
        if self._attempted: raise RuntimeError('YUYV joint preparation already attempted')
        self._attempted = True
        self.api = self.api_factory()
        pair = verify_pair(self.root)['files']
        if __package__: from . import joint_heart_binding as original
        else: import joint_heart_binding as original
        hashes = {'heart_v3b25.bit': pair['heart_v3b25_yuyv.bit'], 'heart_v3b25.hwh': pair['heart_v3b25_yuyv.hwh']}
        with replace_attribute(original, 'PAIR_HASHES', hashes):
            session = super().prepare(base, output, hardware=True)
        try:
            directory = Path(output).parent / 'video'; directory.mkdir(parents=True, exist_ok=False)
            self.video = SharedYuyvResources(self.root, owner=self.owner, identity=self.identity, api=self.api,
                cancelled=lambda: False, on_event=lambda e: None)
            self.video_identity = self.video.open()
            self.video_runner = self.loop_factory(self.video, directory)
            original_begin = session.source.begin
            def begin():
                result = original_begin(); self.video_runner.arm(result['started_ns']); return result
            session.source.begin = begin
            original_stop = session.stop
            def stop(*args, **kwargs):
                self.video_runner.request_stop(); notice = time.monotonic()
                while not self.video_runner.join(.1):
                    if time.monotonic() - notice >= 5:
                        try: print('等待视频线程停止；保留三DMA/CMA/实际锁，不强杀。', flush=True)
                        except BaseException: pass
                        notice = time.monotonic()
                return original_stop(*args, **kwargs)
            session.stop = stop
            session._preflight.update(concurrent_video_target_fps=5, concurrent_display_mode='notebook_heart_hdmi_yuyv_vision',
                video_shares_existing_owner=True, yuyv_joint_binding=True,
                iic_implementation_unchanged=True, processing_exit_strategy_unchanged=True)
            return session
        except BaseException as exc:
            self.prepare_error = describe(exc, 'yuyv_video_prepare')
            try: session._release_owner()
            except BaseException as error: self.release_error = describe(error, 'yuyv_prepare_release')
            raise

    def release(self):
        session = self.session
        callers = [self.video_runner]
        if session is not None:
            callers.extend(getattr(session, '_threads', ()))
            callers.append(getattr(session, '_finalizer', None))
            callers.append(getattr(getattr(session, '_process_chain', None), '_worker', None))
        if any(obj is not None and obj.is_alive() for obj in callers):
            self.quarantine_required = True
            raise RuntimeError('joint callers active; preserve IIC/three DMA/CMA/actual lease')
        if self.video is not None:
            self.video_cleanup = self.video.close()
            self.cleanup = dict(self.video_cleanup['joint'], cleanup_complete=self.video_cleanup['cleanup_complete'])
        else:
            self.cleanup = self.owner.close() if self.owner is not None else dict(cleanup_complete=True, download_attempts=0, dma={})
            if self.cleanup['cleanup_complete'] and self.owner is not None:
                self.owner.release_after_buffers(buffers_released=True)
        self.quarantine_required = bool(not self.cleanup['cleanup_complete'] or self.deferred_lease is not None and self.deferred_lease.held)
        if self.quarantine_required: raise RuntimeError('YUYV joint cleanup not confirmed; preserve resources, no retry')

    def report(self):
        result = super().report()
        result.update(camera_started=bool(self.video and self.video.camera is not None),
            hdmi_started=bool(self.video and self.video.hdmi is not None),
            vision_frame_transferred=bool(self.video and self.video.port and self.video.port.completed),
            video_cleanup=self.video_cleanup, video_identity=self.video_identity,
            quarantine_required=self.quarantine_required,
            actual_lease_released=not bool(self.deferred_lease and self.deferred_lease.held))
        return result

    def native_report(self):
        transport = getattr(self.owner, 'iic_transport', None)
        return dict(schema='v3b25_yuyv_iic_owner_v1', iic=transport.report() if transport else dict(available=False),
            cleanup=self.cleanup, actual_lease_released=not bool(self.deferred_lease and self.deferred_lease.held),
            quarantine_required=self.quarantine_required)
