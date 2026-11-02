"""Qualified route state reuse, over the frozen successful live owner."""
from contextlib import contextmanager, ExitStack
from functools import partial
from route_live_guard import verify_new as verify

ORIGINAL='f76bcbde8997a50db2845b41349be8ec6c06cadfb82203b7f9c3861da45a4cb3'


def verified_ps(connection, backend_source, *, root, expected, **kwargs):
    verify(root,expected)
    from route_recovery_scope import installed as route_scope,Ready
    from state_wire_live_runtime import verified_ps as retained
    with route_scope():
        return retained(Ready(connection),backend_source,root=root,expected=ORIGINAL,**kwargs)


def video_child(spec,*args,expected):
    verify(spec['root'],expected)
    from state_wire_live_runtime import video_child as retained
    return retained(spec,*args,expected=ORIGINAL)


def owner_worker(*args,root,expected,exit_stages,**kwargs):
    verify(root,expected)
    from main_ps_exit_worker import defer_offline_pandas
    with defer_offline_pandas(root),installed(root,expected,exit_stages=exit_stages):
        from compact_video_runtime import worker
        return worker(*args,root=root,**kwargs)


def start_owner(context,*args,root,expected,**kwargs):
    verify(root,expected)
    from lean_ps_exit_trace import make_shared
    process=context.Process(target=partial(owner_worker,root=root,expected=expected,exit_stages=make_shared(),**kwargs),
                            args=args,name='joint25-route-recovery-owner',daemon=False)
    process.start()
    return process


@contextmanager
def parent_scope(root,expected):
    verify(root,expected)
    from joint_startup import replace_attribute
    import video_split_runtime
    with replace_attribute(video_split_runtime,'start_owner',partial(start_owner,expected=expected)):yield


@contextmanager
def installed(root,expected,*,exit_stages=None):
    verify(root,expected)
    from state_wire_live_runtime import installed as retained
    from joint_startup import replace_attribute
    from route_recovery import TAG
    with retained(root,ORIGINAL,exit_stages=exit_stages) as libraries,ExitStack() as stack:
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
            partial(verified_ps,expected=expected,exit_stages=exit_stages)))
        stack.enter_context(replace_attribute(compact_video_process,'run_child',partial(video_child,expected=expected)))
        yield libraries
