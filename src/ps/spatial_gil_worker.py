"""Scope the qualified one-symbol binding to the original joint owner only."""
from contextlib import contextmanager
from functools import partial
from pathlib import Path

if __package__:from .spatial_gil_candidate import bind_transaction as load_candidate
else:from spatial_gil_candidate import bind_transaction as load_candidate


@contextmanager
def install_policy(root,bindings):
    if __package__:
        from . import main_heart_native_build as native
        from .joint_startup import replace_attribute
    else:
        import main_heart_native_build as native
        from joint_startup import replace_attribute
    original=native.load_verified
    root=Path(root).resolve()
    def held_loader(requested):
        if Path(requested).resolve()!=root:raise ValueError('held-GIL loader root differs')
        candidate=load_candidate(original(requested))
        bindings.append(dict(candidate.binding_info))
        return candidate
    with replace_attribute(native,'load_verified',held_loader):yield


def owner_worker(base,directory,mailbox,stop,metrics_ready,*,root,source,manual,manifest_sha,motion_manifest_sha):
    if __package__:
        from .run_gil_joint import verify_package,write_new
        from .main_spatial_worker import owner_worker as original
    else:
        from run_gil_joint import verify_package,write_new
        from main_spatial_worker import owner_worker as original
    verify_package(root);bindings=[];failure=None
    try:
        with install_policy(root,bindings):
            return original(base,directory,mailbox,stop,metrics_ready,root=root,source=source,
                manual=manual,manifest_sha=manifest_sha,motion_manifest_sha=motion_manifest_sha)
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc));raise
    finally:
        identity_error=None
        try:verify_package(root)
        except BaseException as exc:identity_error=dict(type=type(exc).__name__,message=str(exc))
        write_new(Path(directory)/'gil-policy-owner.json',dict(schema='joint_sample_gil_policy_v1',
            bindings=bindings,only_changed_symbol='hm_transact_sample',per_call_new_clocks=0,
            original_error=failure,identity_error=identity_error,original_ps_target_retained=True,
            sensor_video_display_gc_and_protections_retained=True))


def start_owner(context,*args,root,source,manual,manifest_sha,motion_manifest_sha):
    child=context.Process(target=partial(owner_worker,root=root,source=source,manual=manual,
        manifest_sha=manifest_sha,motion_manifest_sha=motion_manifest_sha),args=args,
        name='joint25-main-spatial-held-gil-owner',daemon=False)
    child.start();return child
