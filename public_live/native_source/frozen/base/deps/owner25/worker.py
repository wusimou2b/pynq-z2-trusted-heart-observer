"""The sole hardware owner. Notebook never receives a session or backend handle."""
import json
import os
from pathlib import Path
import sys
import time


def main(root, directory, mailbox, stop, metrics_ready):
    from run_v3a25_owner_display import validate, error, write_new
    directory = Path(directory)
    result = dict(owner_pid=os.getpid(), parent_pid=os.getppid(), summary=None, error=None,
        cleanup_complete=False, hardware_imported=False, backend_fault='', transport=None)
    session = None
    try:
        context, cached = validate(root)
        cached.prepare_runtime(context)
        from pilot25.board import prepare
        from display25.assessment import assess
        session = prepare(Path(root)/'static',directory/'capture',hardware=True)
        session._assess_summary = assess
        session._preflight.update(owner_process_pid=os.getpid(),display_process_pid=os.getppid(),
            owner_manifest_sha256=context['owner_manifest_sha256'])
        if stop.is_set():
            session._request_stop('display_stopped_before_start')
        else:
            session.start()
        while not stop.is_set():
            snap = session.snapshot()
            mailbox.publish(snap)
            if snap.state != 'running': break
            if not 0 <= mailbox.parent_age() <= 2_000_000_000:
                raise TimeoutError('Notebook无进展超过2秒，停止采集；不自动恢复')
            time.sleep(.01)
    except BaseException as exc:
        result['error'] = error(exc,'owner')
        if session is not None:
            session._fail('display_owner',str(exc) or type(exc).__name__)
    finally:
        if session is not None:
            session._request_stop('display_finished')
            try: mailbox.publish(session.snapshot())
            except BaseException as exc: result['error'] = result['error'] or error(exc,'transport_finish')
            metrics = None
            if metrics_ready.wait(5.):
                try:
                    metrics = json.loads((directory/'display_metrics.json').read_text(encoding='utf8'))
                except Exception as exc: result['error'] = result['error'] or error(exc,'display_metrics')
            else:
                result['error'] = result['error'] or error(TimeoutError('未收到显示结束审计'),'display_metrics')
            try:
                from display25.runner import _stop
                result['summary'], cleanup_error = _stop(session,metrics)
                result['error'] = result['error'] or cleanup_error
                result['cleanup_complete'] = result['summary']['cleanup_complete']
                result['backend_fault'] = getattr(session.backend,'_fault','')
            except BaseException as exc:
                # Never label an exception as confirmed hardware release.
                result['error'] = result['error'] or error(exc,'owner_cleanup')
        else:
            # prepare() owns its failure cleanup contract; no session was returned.
            result['cleanup_complete'] = False
        result['hardware_imported'] = any(n == 'pynq' or n.startswith('pynq.') for n in sys.modules)
        result['transport'] = mailbox.stats()
        write_new(directory/'owner_result.json',result)
