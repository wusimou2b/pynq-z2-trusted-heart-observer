"""Scoped additive candidate; original package/guards remain independently verifiable."""
from contextlib import contextmanager,ExitStack
from functools import partial
from pathlib import Path
import importlib,json


def check(root,expected,release_contract=None):
    if release_contract is not None:
        from public_live_identity import check_runtime
        return check_runtime(root,release_contract)
    from compact_delivery_guard import verify
    return verify(root,expected)


def preview_verify(spec):check(spec['root'],spec['compact_sha256'],spec.get('release_contract'))


def preview_handler(spec,control):
    with installed(spec['root'],spec['compact_sha256'],release_contract=spec.get('release_contract')):
        import compact_run_video_split as entry
        return entry._run_owned_preview20(expected_manifest_sha256=spec['manifest_sha256'],control=control,
            startup_deadline_ns=spec['startup_deadline_ns'],release_contract=spec.get('release_contract'))


def video_child(spec,*args):
    # Child validates both manifests before driver imports or constructing any resource.
    with installed(spec['root'],spec['compact_sha256'],video_only=True,release_contract=spec.get('release_contract')):
        from compact_video_process import retained_run_child
        return retained_run_child(spec,*args)


def verified_ps(connection,backend_source,*,root,compact_sha256,delegate,manifest_sha256,release_contract=None,**kwargs):
    check(root,compact_sha256,release_contract)
    from joint_startup import replace_attribute
    import main_spatial_ps
    from main_rpc_compact import ps_worker
    # Keep all original spawn identity wrappers and ReadyConnection metadata.
    with replace_attribute(main_spatial_ps,'main_worker',ps_worker):
        if release_contract is not None:kwargs['release_contract']=release_contract
        return delegate(connection,backend_source,root=root,**kwargs)


def owner_worker(*args,root,compact_sha256,release_contract=None,**kwargs):
    with installed(root,compact_sha256,release_contract=release_contract):
        from compact_video_runtime import worker
        if release_contract is not None:kwargs['release_contract']=release_contract
        return worker(*args,root=root,**kwargs)


def start_owner(context,*args,root,compact_sha256,release_contract=None,**kwargs):
    check(root,compact_sha256,release_contract)
    p=context.Process(target=partial(owner_worker,root=root,compact_sha256=compact_sha256,release_contract=release_contract,**kwargs),
        args=args,name='joint25-compact-timeout-owner',daemon=False)
    p.start();return p


@contextmanager
def installed(root,expected,*,video_only=False,release_contract=None):
    root=Path(root).resolve();check(root,expected,release_contract)
    from joint_startup import replace_attribute
    # Import retained verifier aliases before selecting a different physical pair.
    # They continue to verify the preserved reference bytes, not this candidate.
    import main_spatial_guard,main_spatial_owner,main_heart_guard,main_spatial_runtime
    import main_spatial_assessment,main_heart_native_build,video_split_runtime,video_split_process,video_split_preview
    import compact_board_owner,compact_video_process,compact_video_runtime
    from compact_delivery_guard import verify_release as legacy_release,native_module
    def verify_release(directory):
        if release_contract is None:return legacy_release(directory)
        from public_live_identity import verify_hardware
        return verify_hardware(directory,release_contract)
    target=root/'compact_hardware'
    original_hardware=main_spatial_owner.Hardware
    class Hardware(original_hardware):
        def __init__(self,bit_path):
            path=Path(bit_path).resolve()
            if path not in (root/'hardware/heart_v3b25_main.bit',target/'heart_v3b25_main.bit'):
                raise ValueError('unexpected physical pair request')
            verify_release(target)
            super().__init__(target/'heart_v3b25_main.bit')
    class Owner(compact_board_owner.IntegratedOwner):
        def __init__(self,directory,**kwargs):
            if Path(directory).resolve() not in (root/'hardware',target):raise ValueError('unexpected owner directory')
            super().__init__(target,hardware_factory=Hardware,**kwargs)
    def release(directory):
        if Path(directory).resolve() not in (root/'hardware',target):raise ValueError('unexpected release directory')
        return verify_release(target)
    def video_factory(ctx,spec,channel,**kwargs):
        return compact_video_process.ProcessVideo(ctx,dict(spec,compact_sha256=expected,release_contract=release_contract),channel,**kwargs)
    class Preview(video_split_preview.PreviewSession):
        def __init__(self,ctx,spec,**kwargs):
            super().__init__(ctx,dict(spec,compact_sha256=expected,release_contract=release_contract),verify=preview_verify,handler=preview_handler,**kwargs)
    with ExitStack() as stack:
        for obj,name,value in ((main_spatial_owner,'Hardware',Hardware),
            (main_spatial_owner,'IntegratedOwner',Owner),(compact_board_owner,'verify_release',release),
            (main_heart_guard,'verify_release',release),(video_split_process,'ProcessVideo',video_factory),
            (compact_video_runtime,'ProcessVideo',video_factory),(video_split_preview,'PreviewSession',Preview)):
            stack.enter_context(replace_attribute(obj,name,value))
        if not video_only:
            import main_heart_process,journal60_runtime
            import main_rpc_compact,compact_timeout_driver,compact_spatial_assessment
            import status60_ab_runtime
            from compact_context_binding import paired_bind
            def load_native(_,**loader_kwargs):
                selected_contract=loader_kwargs.pop('release_contract',release_contract)
                if loader_kwargs or selected_contract!=release_contract:
                    raise ValueError('compact native loader contract differs from installed scope')
                if release_contract is None:return native_module(root).load_verified(root/'compact_native')
                return native_module(root).load_verified(root/'compact_native',release_contract=release_contract)
            for obj,name,value in ((status60_ab_runtime.Activation,'bind',paired_bind(status60_ab_runtime.Activation.bind)),
                (main_heart_native_build,'load_verified',load_native),
                (journal60_runtime,'Native40Main',compact_timeout_driver.TimeoutMain),
                (main_spatial_runtime,'LiveBackend',compact_timeout_driver.LiveBackend),
                (main_spatial_assessment,'assess_video',compact_spatial_assessment.assess_video),
                (main_heart_process,'Bridge',main_rpc_compact.Bridge),
                (compact_video_runtime,'verified_heart_entry',partial(verified_ps,compact_sha256=expected,release_contract=release_contract)),
                (video_split_runtime,'start_owner',partial(start_owner,compact_sha256=expected,release_contract=release_contract))):
                stack.enter_context(replace_attribute(obj,name,value))
        try:yield
        finally:check(root,expected,release_contract)
