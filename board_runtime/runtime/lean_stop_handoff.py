"""Stop-state handoff only; retained owner loop, deadlines and DMA cleanup."""
import json
from pathlib import Path
import time


def owner_main(binding,root,directory,mailbox,stop,metrics_ready,*,dependencies=None,sleep=time.sleep,emit=print):
    # Same original loop/heartbeat/Session.stop. Only the video stop barrier is
    # now explicitly loop_stopped, while the child remains alive owning CMA.
    import joint_concurrent_owner as original
    import os,sys
    d=dependencies or original._dependencies();directory=Path(directory);session=None
    result=dict(owner_pid=os.getpid(),parent_pid=os.getppid(),summary=None,error=None,cleanup_complete=False,
        hardware_imported=False,backend_fault='',transport=None,video_thread_joined=False,
        video_loop_stopped=False,video_process_exited=False,video_join_seconds=None)
    try:
        context,cached=d.bootstrap(root,algorithm=True)
        session=d.prepare(Path(root)/'deps/static/checked/base',directory/'capture',hardware=True)
        session._assess_summary=d.assess
        session._preflight.update(owner_process_pid=os.getpid(),display_process_pid=os.getppid(),
            owner_manifest_sha256=context['owner_manifest_sha256'],effective_manifest_sha256=context['effective_manifest_sha256'])
        binding.video_runner.start()
        if stop.is_set():session._request_stop('display_stopped_before_start')
        else:session.start()
        while not stop.is_set():
            binding.video_runner.heartbeat()
            snap=session.snapshot();mailbox.publish(snap)
            if binding.video_runner.fault:raise RuntimeError('joint video failed: '+binding.video_runner.fault['message'])
            if snap.state!='running':break
            if not 0<=mailbox.parent_age()<=2_000_000_000:
                raise TimeoutError('Notebook无进展超过2秒，停止联合试验；不自动恢复')
            sleep(.01)
    except BaseException as exc:
        result['error']=original.error(exc,'concurrent_owner')
        if session is not None:session._fail('display_owner',str(exc) or type(exc).__name__)
    finally:
        if session is not None:session._request_stop('display_finished')
        # Publish stopping before the potentially blocking video barrier.
        # Keep the original later snapshot so late faults remain in the report.
        if session is not None:
            try:mailbox.publish(session.snapshot())
            except BaseException as exc:result['error']=result['error'] or original.error(exc,'transport_stop_handoff')
        runner=binding.video_runner
        if runner is not None:
            runner.request_stop();began=notice=time.monotonic()
            while not runner.wait_loop_stopped(.1):
                if time.monotonic()-notice>=5:
                    emit('等待视频调用返回；保留DMA/CMA/租约，不强杀。',flush=True);notice=time.monotonic()
            result.update(video_loop_stopped=True,video_join_seconds=time.monotonic()-began)
            if runner.fault and session is not None:
                result['error']=result['error'] or dict({'stage':'video_process'},**runner.fault)
                session._fail('joint_video',runner.fault['message'])
        if session is not None:
            try:mailbox.publish(session.snapshot())
            except BaseException as exc:result['error']=result['error'] or original.error(exc,'transport_finish')
            metrics=None
            if metrics_ready.wait(5.):
                try:metrics=json.loads((directory/'display_metrics.json').read_text('utf-8'))
                except Exception as exc:result['error']=result['error'] or original.error(exc,'display_metrics')
            else:result['error']=result['error'] or original.error(TimeoutError('未收到显示结束审计'),'display_metrics')
            try:
                result['summary'],cleanup_error=d.stop(session,metrics)
                result['error']=result['error'] or cleanup_error
                result['cleanup_complete']=bool(result['summary']['cleanup_complete'] and (binding.video_cleanup or {}).get('cleanup_complete'))
                result['backend_fault']=getattr(session.backend,'_fault','')
            except BaseException as exc:result['error']=result['error'] or original.error(exc,'owner_cleanup')
        result['video_process_exited']=bool(runner and runner.process and not runner.is_alive())
        result['video_thread_joined']=result['video_process_exited']
        result['hardware_imported']=any(n=='pynq' or n.startswith('pynq.') for n in sys.modules)
        result['transport']=mailbox.stats();d.write_new(directory/'owner_result.json',result)
