"""Original heart-owner cadence with explicit video join before heart finalization."""
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace


def error(exc,stage):return dict(stage=stage,type=type(exc).__name__,message=str(exc))


def _dependencies():
    from effective25.identity import bootstrap,write_new
    def prepare(*a,**k):
        from effective25.board import prepare as original
        return original(*a,**k)
    def assess(*a,**k):
        from effective25.display_assessment import assess as original
        return original(*a,**k)
    def stop(*a,**k):
        from display25.runner import _stop
        return _stop(*a,**k)
    return SimpleNamespace(bootstrap=bootstrap,write_new=write_new,prepare=prepare,assess=assess,stop=stop)


def owner_main(binding,root,directory,mailbox,stop,metrics_ready,*,dependencies=None,sleep=time.sleep,emit=print):
    d=dependencies or _dependencies();directory=Path(directory);session=None
    result=dict(owner_pid=os.getpid(),parent_pid=os.getppid(),summary=None,error=None,cleanup_complete=False,
        hardware_imported=False,backend_fault='',transport=None,video_thread_joined=False,video_join_seconds=None)
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
            snap=session.snapshot();mailbox.publish(snap)
            if binding.video_runner.fault:raise RuntimeError('joint video failed: '+binding.video_runner.fault['message'])
            if snap.state!='running':break
            if not 0<=mailbox.parent_age()<=2_000_000_000:
                raise TimeoutError('Notebook无进展超过2秒，停止联合试验；不自动恢复')
            sleep(.01)
    except BaseException as exc:
        result['error']=error(exc,'concurrent_owner')
        if session is not None:session._fail('display_owner',str(exc) or type(exc).__name__)
    finally:
        if session is not None:session._request_stop('display_finished')
        runner=binding.video_runner
        if runner is not None:
            runner.request_stop();began=last_notice=time.monotonic()
            while not runner.join(.1):
                # Native I/O cannot safely be killed. Keep all references/lease;
                # do not enter Session.stop/GC finalization while video is active.
                if time.monotonic()-last_notice>=5:
                    try:emit('等待视频线程停止；保留共享所有者、CMA和锁，不强杀。',flush=True)
                    except BaseException:pass
                    last_notice=time.monotonic()
            result.update(video_thread_joined=True,video_join_seconds=time.monotonic()-began)
            if runner.fault and session is not None:
                result['error']=result['error'] or dict({'stage':'video_thread'},**runner.fault)
                session._fail('joint_video',runner.fault['message'])
        if session is not None:
            try:mailbox.publish(session.snapshot())
            except BaseException as exc:result['error']=result['error'] or error(exc,'transport_finish')
            metrics=None
            if metrics_ready.wait(5.):
                try:metrics=json.loads((directory/'display_metrics.json').read_text(encoding='utf-8'))
                except Exception as exc:result['error']=result['error'] or error(exc,'display_metrics')
            else:result['error']=result['error'] or error(TimeoutError('未收到显示结束审计'),'display_metrics')
            try:
                result['summary'],cleanup_error=d.stop(session,metrics)
                result['error']=result['error'] or cleanup_error
                result['cleanup_complete']=bool(result['summary']['cleanup_complete'] and
                    (binding.video_cleanup or {}).get('cleanup_complete'))
                result['backend_fault']=getattr(session.backend,'_fault','')
            except BaseException as exc:result['error']=result['error'] or error(exc,'owner_cleanup')
        result['hardware_imported']=any(n=='pynq' or n.startswith('pynq.') for n in sys.modules)
        result['transport']=mailbox.stats()
        d.write_new(directory/'owner_result.json',result)
