"""Cold spawn target; original Lean PS target and original lifetime stay intact."""
from functools import partial
from pathlib import Path


def owner_worker(base,directory,mailbox,stop,metrics_ready,*,root,source,manual,manifest_sha,shadow_manifest_sha):
    if __package__:
        from .shadow_guard import verify_package
        from .shadow_fusion import ShadowFusion
        from .shadow_joint import ShadowBinding,TappedMailbox
        from .joint_startup import replace_attribute
        from .lean_ps_guard import write_new
        from . import continuous_runtime as original,heart_video_binding as binding
    else:
        from shadow_guard import verify_package
        from shadow_fusion import ShadowFusion
        from shadow_joint import ShadowBinding,TappedMailbox
        from joint_startup import replace_attribute
        from lean_ps_guard import write_new
        import continuous_runtime as original,heart_video_binding as binding
    verify_package(root,shadow_manifest_sha)
    fusion=ShadowFusion();instances=[];failure=None
    class OwnedShadowBinding(ShadowBinding):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,fusion=fusion,**kwargs)
            instances.append(self)
    try:
        with replace_attribute(binding,'SnapshotVideoBinding',OwnedShadowBinding):
            original.owner_worker(base,directory,TappedMailbox(mailbox,fusion),stop,metrics_ready,
                root=root,source=source,manual=manual,manifest_sha=manifest_sha)
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        identity_error=None
        try:verify_package(root,shadow_manifest_sha)
        except BaseException as exc:identity_error=dict(type=type(exc).__name__,message=str(exc))
        writer_stopped=bool(len(instances)==1 and instances[0].video_runner is not None and not instances[0].video_runner.is_alive())
        # Only bounded in-memory counters; never inspect a possibly active video journal.
        write_new(Path(directory)/'shadow-owner.json',dict(schema='v3b25_shadow_owner_v1',wrapper_error=failure,
            identity_error=identity_error,inputs_unchanged=identity_error is None,binding_instances=len(instances),
            video_writer_stopped=writer_stopped,shadow=fusion.report(),heart_control_enabled=False,
            original_ps_target_retained=True,original_gc_and_exit_strategy_retained=True))


def start_owner(context,*args,root,source,manual,manifest_sha,shadow_manifest_sha):
    child=context.Process(target=partial(owner_worker,root=root,source=source,manual=manual,
        manifest_sha=manifest_sha,shadow_manifest_sha=shadow_manifest_sha),args=args,
        name='joint25-shadow-spatial-owner',daemon=False)
    child.start()
    return child
