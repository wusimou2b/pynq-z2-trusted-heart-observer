"""Child spawn hooks for the shared-owner pilot; cold module has no board imports."""
from contextlib import contextmanager
from functools import partial
import json
import os
from pathlib import Path
import sys
import time


@contextmanager
def install_owner_main(module,replacement):
    original=module.main;module.main=replacement
    try:yield
    finally:module.main=original


def retention_reasons(binding):
    reasons=[];runner=binding.video_runner;session=binding.session;video=binding.video
    if runner is not None and runner.is_alive():reasons.append('video_thread_active')
    if session is not None:
        if any(t.is_alive() for t in getattr(session,'_threads',())):reasons.append('heart_thread_active')
        finalizer=getattr(session,'_finalizer',None)
        if finalizer is not None and finalizer.is_alive():reasons.append('heart_finalizer_active')
        process=getattr(getattr(session,'_process_chain',None),'_worker',None)
        if process is not None and process.is_alive():reasons.append('ps_child_active')
    if binding.deferred_lease is not None and binding.deferred_lease.held:reasons.append('actual_lease_held')
    if video is not None and (video.buffer is not None or video.pending is not None):reasons.append('video_buffer_retained')
    if binding.quarantine_required:reasons.append('hardware_quarantine_required')
    return reasons


def retain_if_unsafe(binding,*,sleep=time.sleep,emit=print):
    reasons=retention_reasons(binding)
    if not reasons:return
    try:emit('QUARANTINE: '+','.join(reasons)+'；保留所有者/缓冲/锁，不强杀；不要关闭内核或运行其他入口。',flush=True)
    except BaseException:pass
    # No implicit retry of DMA stop/free/lease release from this backstop.
    while True:sleep(1)


def system_resources():
    value=dict(maxrss=None,maxrss_scope='owner process only, OS units; not aggregate PS child or Notebook RSS',
        memory_swap_lines=[],errors=[])
    try:
        import resource
        value['maxrss']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception as exc:value['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
    try:
        value['memory_swap_lines']=[line for line in Path('/proc/meminfo').read_text().splitlines()
            if line.split(':',1)[0] in {'MemTotal','MemAvailable','SwapTotal','SwapFree'}]
    except Exception as exc:value['errors'].append(dict(type=type(exc).__name__,message=str(exc)))
    return value


def finish_reports(root,directory,binding,*,failure=None,verify=None):
    if __package__:
        from .joint_heart_guard import sha,write_new
    else:
        from joint_heart_guard import sha,write_new
    if verify is None:
        if __package__:from .joint_concurrent_guard import verify_concurrent as verify
        else:from joint_concurrent_guard import verify_concurrent as verify
    directory=Path(directory);owner_path=directory/'owner_result.json'
    owner=json.loads(owner_path.read_text(encoding='utf-8')) if owner_path.is_file() else {}
    unchanged=True;identity_error=None
    try:verify(root)
    except BaseException as exc:
        unchanged=False;identity_error=dict(stage='postrun_identity',type=type(exc).__name__,message=str(exc))
    video=None
    if binding.video_runner is not None:
        video=binding.video_runner.report()
        video.update(identity=binding.video_identity,cleanup=binding.video_cleanup or {},inputs_unchanged=unchanged,
            publication_error=None,post_verification=dict(attempted=False,matched=False))
        if binding.video_cleanup and binding.video_cleanup.get('cleanup_complete') and not retention_reasons(binding):
            try:video['post_verification']=binding.video.post_verify()
            except BaseException as exc:
                video['fault']=video['fault'] or dict(stage='post_cleanup_reference',type=type(exc).__name__,message=str(exc))
        video['fault']=video['fault'] or identity_error
        journal=directory/'video/frames.jsonl'
        video['frames_sha256']=sha(journal) if journal.is_file() else None
        write_new(directory/'video/worker_result.json',video)
    result=dict(schema='v3b25_concurrent_owner_v1',owner_pid=os.getpid(),parent_pid=os.getppid(),
        binding_installed=binding.prepare_calls==1,
        wrapper_error=failure,inherited_cleanup_complete=owner.get('cleanup_complete',False),
        video_thread_joined=bool(binding.video_runner and not binding.video_runner.is_alive()),
        inputs_unchanged=unchanged,identity_error=identity_error,retention_reasons=retention_reasons(binding),
        system_resources=system_resources(),video=video,**binding.report())
    write_new(directory/'concurrent_owner_result.json',result)
    return result


def worker(base,directory,mailbox,stop,metrics_ready):
    root=Path(__file__).resolve().parent;binding=None;failure=None
    try:
        from joint_concurrent_guard import verify_concurrent
        verify_concurrent(root)
        frozen=root/'frozen'
        if str(frozen) not in sys.path:sys.path.insert(0,str(frozen))
        from entry25_guard import validate,activate
        validate(frozen);activate(frozen)
        from joint_concurrent_binding import ConcurrentBinding
        from joint_concurrent_owner import owner_main
        from joint_heart_worker import install_binding
        from effective25 import owner as inherited_owner
        import run_entry25_live as inherited
        binding=ConcurrentBinding(root)
        with install_binding(binding),install_owner_main(inherited_owner,partial(owner_main,binding)):
            inherited.entry_owner(base,directory,mailbox,stop,metrics_ready)
    except BaseException as exc:
        failure=dict(type=type(exc).__name__,message=str(exc))
        raise
    finally:
        if binding is not None:
            try:finish_reports(root,directory,binding,failure=failure)
            finally:retain_if_unsafe(binding)


def start_owner(context,base,directory,mailbox,stop,metrics_ready):
    process=context.Process(target=worker,args=(base,directory,mailbox,stop,metrics_ready),
        name='joint-effective25-fivefps-owner',daemon=False)
    process.start()
    return process
