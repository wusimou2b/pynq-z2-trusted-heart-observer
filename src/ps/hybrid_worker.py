"""Cold spawn target: add text inside the original complete-motion owner."""
from functools import partial
from pathlib import Path


def owner_worker(base,directory,mailbox,stop,metrics_ready,*,root,source,manual,manifest_sha,hybrid_manifest_sha):
    if __package__:
        from .hybrid_guard import verify_package
        from .hybrid_display import HybridBinding, HybridMailbox
        from .hdmi_dashboard_model import DashboardModel
        from .joint_startup import replace_attribute
        from .lean_ps_guard import write_new,sha
        from . import video_motion_worker as original,video_motion_joint,shadow_joint
    else:
        from hybrid_guard import verify_package
        from hybrid_display import HybridBinding, HybridMailbox
        from hdmi_dashboard_model import DashboardModel
        from joint_startup import replace_attribute
        from lean_ps_guard import write_new,sha
        import video_motion_worker as original,video_motion_joint,shadow_joint
    verify_package(root,hybrid_manifest_sha)
    model=DashboardModel();bindings=[];failure=None
    class BoundBinding(HybridBinding):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,model=model,**kwargs)
            bindings.append(self)
    try:
        with replace_attribute(video_motion_joint,'MotionBinding',BoundBinding), \
             replace_attribute(shadow_joint,'TappedMailbox',partial(HybridMailbox,model=model)):
            original.owner_worker(base,directory,mailbox,stop,metrics_ready,root=root,source=source,
                manual=manual,manifest_sha=manifest_sha,
                motion_manifest_sha=sha(Path(root)/'full-motion-manifest.json'))
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        error=None
        try:verify_package(root,hybrid_manifest_sha)
        except BaseException as exc:error=dict(type=type(exc).__name__,message=str(exc))
        video=bindings[0].video if len(bindings)==1 else None
        runner=bindings[0].video_runner if len(bindings)==1 else None
        write_new(Path(directory)/'hybrid-owner.json',dict(schema='v3b25_hybrid_owner_v1',
            inputs_unchanged=error is None,identity_error=error,wrapper_error=failure,
            binding_instances=len(bindings),video_writer_stopped=bool(runner is not None and not runner.is_alive()),
            display=video.hybrid_report() if video is not None else None,model=model.report(),
            browser_graphics_enabled=True,original_ps_target_retained=True,
            original_start_gc_exit_and_protections_retained=True))


def start_owner(context,*args,root,source,manual,manifest_sha,motion_manifest_sha):
    child=context.Process(target=partial(owner_worker,root=root,source=source,manual=manual,
        manifest_sha=manifest_sha,hybrid_manifest_sha=motion_manifest_sha),args=args,
        name='joint25-hybrid-display-owner',daemon=False)
    child.start()
    return child
