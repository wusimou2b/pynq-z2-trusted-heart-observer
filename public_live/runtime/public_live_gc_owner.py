"""Original GC observer/window around the explicitly verified public owner."""
import json
import os
from pathlib import Path
from public_live_contract import verify_release


def run_owner(base, directory, mailbox, stop, metrics_ready, *, release_contract):
    context = verify_release(release_contract)
    if Path(base).resolve() != Path(context['runtime_root']) / 'frozen/base':
        raise ValueError('public GC owner base differs from release')
    from effective25 import board, owner
    from effective25_gc_log import GCLog
    from effective25_gc_window import Window, install_session, memory_snapshot
    directory = Path(directory)
    window = Window()
    log = GCLog()
    original_prepare = board.prepare
    undo = None
    install_error = failure = None

    def prepare(*args, **kwargs):
        nonlocal undo, install_error
        session = original_prepare(*args, **kwargs)
        try:
            undo = install_session(session, window)
        except BaseException as exc:
            install_error = dict(type=type(exc).__name__, message=str(exc))
            session._fail('gc_window_install', str(exc))
        return session

    board.prepare = prepare
    try:
        log.start()
        return owner.main(base, directory, mailbox, stop, metrics_ready)
    except BaseException as exc:
        failure = dict(type=type(exc).__name__, message=str(exc))
        raise
    finally:
        log.stop()
        board.prepare = original_prepare
        window.restore('owner_finally_fallback')
        if undo is not None:
            undo()
        owner_path = directory / 'owner_result.json'
        owner_result = json.loads(owner_path.read_text('utf-8')) if owner_path.is_file() else {}
        common = dict(release_manifest_sha256=context['manifest_sha256'],
            historical_numerical_qualification=False, owner_pid=os.getpid(),
            parent_pid=os.getppid(), wrapper_error=failure)
        values = {
            'owner_gc.json': dict(common, schema='trusted_heart_public_owner_gc_v1',
                capture_cleanup_complete=owner_result.get('cleanup_complete', False), gc=log.report()),
            'owner_gc_window.json': dict(common, schema='trusted_heart_public_gc_window_v1',
                window=window.report(), install_error=install_error,
                memory_after_cleanup=memory_snapshot()),
        }
        for name, value in values.items():
            with (directory / name).open('x', encoding='utf-8') as sink:
                json.dump(value, sink, ensure_ascii=False, indent=2, allow_nan=False)
