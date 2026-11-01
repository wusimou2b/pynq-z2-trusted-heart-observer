"""The existing hybrid owner with a scoped main-heart backend installation."""
from public_live_lower_identity import verify_boundary, public_prepared
from functools import partial
from pathlib import Path

def owner_worker(base, directory, mailbox, stop, metrics_ready, *, root, source, manual, manifest_sha, motion_manifest_sha, release_contract=None):
    if release_contract is not None:
        manifest_sha = release_contract['expected_manifest_sha256']
        motion_manifest_sha = release_contract['expected_manifest_sha256']
    if __package__:
        from .main_spatial_guard import verify_package
        from .main_spatial_runtime import install_main_runtime
        from . import hybrid_display, continuous_runtime, heart_video_binding
        from .shadow_fusion import ShadowFusion
        from .hdmi_dashboard_model import DashboardModel
        from .joint_startup import replace_attribute
        from .lean_ps_guard import write_new
    else:
        from main_spatial_guard import verify_package
        from main_spatial_runtime import install_main_runtime
        import hybrid_display, continuous_runtime, heart_video_binding
        from shadow_fusion import ShadowFusion
        from hdmi_dashboard_model import DashboardModel
        from joint_startup import replace_attribute
        from lean_ps_guard import write_new
    verify_package(root, motion_manifest_sha) if release_contract is None else verify_boundary(root, release_contract)
    fusion = ShadowFusion()
    model = DashboardModel()
    instances = []
    failure = None
    try:
        with install_main_runtime(root, source, release_contract=release_contract):

            class BoundBinding(hybrid_display.HybridBinding):

                def __init__(self, *args, **kwargs):
                    super().__init__(*args, fusion=fusion, model=model, **kwargs)
                    instances.append(self)
            observed = hybrid_display.HybridMailbox(mailbox, fusion, model=model)
            with replace_attribute(heart_video_binding, 'SnapshotVideoBinding', BoundBinding):
                continuous_runtime.owner_worker(base, directory, observed, stop, metrics_ready, root=root, source=source, manual=manual, manifest_sha=manifest_sha, release_contract=release_contract)
    except BaseException as exc:
        failure = dict(type=type(exc).__name__, message=str(exc))
        raise
    finally:
        identity_error = None
        try:
            verify_package(root, motion_manifest_sha) if release_contract is None else verify_boundary(root, release_contract)
        except BaseException as exc:
            identity_error = dict(type=type(exc).__name__, message=str(exc))
        video = instances[0].video if len(instances) == 1 else None
        runner = instances[0].video_runner if len(instances) == 1 else None
        common = dict(inputs_unchanged=identity_error is None, identity_error=identity_error, wrapper_error=failure, binding_instances=len(instances), video_writer_stopped=bool(runner is not None and (not runner.is_alive())), original_ps_target_retained=False, main_heart_target='one_sample_continuous_v1', original_start_gc_exit_and_protections_retained=True)
        write_new(Path(directory) / 'motion-owner.json', dict(common, schema='v3b25_main_spatial_motion_owner_v1', fusion=fusion.report(), preparation_hdmi_submissions=getattr(video, 'preparation_submissions', 0), original_start_order_retained=True, original_gc_and_exit_strategy_retained=True, heart_control_enabled=False, per_register_timing_enabled=False))
        write_new(Path(directory) / 'hybrid-owner.json', dict(common, schema='v3b25_main_spatial_hybrid_owner_v1', display=video.hybrid_report() if video else None, model=model.report(), browser_graphics_enabled=True))

def start_owner(context, *args, root, source, manual, manifest_sha, motion_manifest_sha, release_contract=None):
    if release_contract is not None:
        manifest_sha = release_contract['expected_manifest_sha256']
        motion_manifest_sha = release_contract['expected_manifest_sha256']
    child = context.Process(target=partial(owner_worker, root=root, source=source, manual=manual, manifest_sha=manifest_sha, motion_manifest_sha=motion_manifest_sha, release_contract=release_contract), args=args, name='joint25-main-spatial-hybrid-owner', daemon=False)
    child.start()
    return child
