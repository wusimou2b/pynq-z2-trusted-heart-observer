"""Qualified route state reuse, over the frozen successful live owner."""
from contextlib import contextmanager, ExitStack
from functools import partial
from route_live_guard import verify_new as verify

ORIGINAL='b0b16709a497dba4cb05d381814b76ccfc3fb9d15c1039a970e1cef7525d35c8'

def check(root,expected,release_contract=None):
    if release_contract is None:return verify(root,expected)
    from public_live_identity import check_runtime
    return check_runtime(root,release_contract)


def verified_ps(connection, backend_source, *, root, expected, release_contract=None, **kwargs):
    check(root,expected,release_contract)
    from route_recovery_scope import installed as route_scope,Ready
    from state_wire_live_runtime import verified_ps as retained
    with route_scope():
        if release_contract is not None:kwargs['release_contract']=release_contract
        return retained(Ready(connection),backend_source,root=root,expected=ORIGINAL,**kwargs)


def video_child(spec,*args,expected,release_contract=None):
    release_contract=spec.get('release_contract',release_contract)
    check(spec['root'],expected,release_contract)
    from state_wire_live_runtime import video_child as retained
    return retained(spec,*args,expected=ORIGINAL,release_contract=release_contract)


def owner_worker(*args,root,expected,exit_stages,release_contract=None,**kwargs):
    check(root,expected,release_contract)
    from main_ps_exit_worker import defer_offline_pandas
    with defer_offline_pandas(root),installed(root,expected,exit_stages=exit_stages,release_contract=release_contract):
        from compact_video_runtime import worker
        if release_contract is not None:kwargs['release_contract']=release_contract
        return worker(*args,root=root,**kwargs)


def start_owner(context,*args,root,expected,release_contract=None,**kwargs):
    check(root,expected,release_contract)
    from lean_ps_exit_trace import make_shared
    process=context.Process(target=partial(owner_worker,root=root,expected=expected,exit_stages=make_shared(),release_contract=release_contract,**kwargs),
                            args=args,name='joint25-route-recovery-owner',daemon=False)
    process.start()
    return process


@contextmanager
def parent_scope(root,expected,release_contract=None):
    check(root,expected,release_contract)
    from joint_startup import replace_attribute
    import video_split_runtime
    with replace_attribute(video_split_runtime,'start_owner',partial(start_owner,expected=expected,release_contract=release_contract)):yield


@contextmanager
def installed(root,expected,*,exit_stages=None,release_contract=None):
    check(root,expected,release_contract)
    from state_wire_live_runtime import installed as retained
    from joint_startup import replace_attribute
    from route_recovery import TAG
    with retained(root,ORIGINAL,exit_stages=exit_stages,release_contract=release_contract) as libraries,ExitStack() as stack:
        import compact_video_runtime,compact_video_process,main_heart_process
        factory=main_heart_process.Bridge
        def bridge(*a,**k):
            result=factory(*a,**k)
            if result.info().get('route_output_policy')!=TAG:
                result.close()
                raise RuntimeError('route recovery READY identity differs')
            return result
        stack.enter_context(replace_attribute(main_heart_process,'Bridge',bridge))
        stack.enter_context(replace_attribute(compact_video_runtime,'verified_heart_entry',
            partial(verified_ps,expected=expected,exit_stages=exit_stages,release_contract=release_contract)))
        stack.enter_context(replace_attribute(compact_video_process,'run_child',partial(video_child,expected=expected,release_contract=release_contract)))
        yield libraries
