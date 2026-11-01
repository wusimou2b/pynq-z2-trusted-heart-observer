"""Cold spawn target; the successful continuous owner's startup order is unchanged."""
from functools import partial
from pathlib import Path


def owner_worker(base,directory,mailbox,stop,metrics_ready,*,root,source,manual,manifest_sha,motion_manifest_sha):
    if __package__:
        from .video_motion_guard import verify_package
        from .video_motion_joint import MotionBinding
        from .shadow_fusion import ShadowFusion
        from .shadow_joint import TappedMailbox
        from .joint_startup import replace_attribute
        from .lean_ps_guard import write_new
        from . import continuous_runtime as original, heart_video_binding as binding
    else:
        from video_motion_guard import verify_package
        from video_motion_joint import MotionBinding
        from shadow_fusion import ShadowFusion
        from shadow_joint import TappedMailbox
        from joint_startup import replace_attribute
        from lean_ps_guard import write_new
        import continuous_runtime as original, heart_video_binding as binding
    verify_package(root,motion_manifest_sha)
    fusion=ShadowFusion(); instances=[]; failure=None
    class OwnedMotionBinding(MotionBinding):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,fusion=fusion,**kwargs)
            instances.append(self)
    try:
        with replace_attribute(binding,'SnapshotVideoBinding',OwnedMotionBinding):
            original.owner_worker(base,directory,TappedMailbox(mailbox,fusion),stop,metrics_ready,
                root=root,source=source,manual=manual,manifest_sha=manifest_sha)
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        identity_error=None
        try: verify_package(root,motion_manifest_sha)
        except BaseException as exc: identity_error=dict(type=type(exc).__name__,message=str(exc))
        video=instances[0].video if len(instances)==1 else None
        runner=instances[0].video_runner if len(instances)==1 else None
        write_new(Path(directory)/'motion-owner.json',dict(schema='v3b25_baseline_full_motion_owner_v1',
            inputs_unchanged=identity_error is None,identity_error=identity_error,wrapper_error=failure,
            binding_instances=len(instances),video_writer_stopped=bool(runner is not None and not runner.is_alive()),
            fusion=fusion.report(),preparation_hdmi_submissions=getattr(video,'preparation_submissions',0),
            original_ps_target_retained=True,original_start_order_retained=True,
            original_gc_and_exit_strategy_retained=True,heart_control_enabled=False,per_register_timing_enabled=False))


def start_owner(context,*args,root,source,manual,manifest_sha,motion_manifest_sha):
    child=context.Process(target=partial(owner_worker,root=root,source=source,manual=manual,
        manifest_sha=manifest_sha,motion_manifest_sha=motion_manifest_sha),args=args,
        name='joint25-baseline-full-motion-owner',daemon=False)
    child.start()
    return child
