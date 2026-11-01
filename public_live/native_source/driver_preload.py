"""One owner-local import thread; the original factory and hardware order stay intact."""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import time


def describe(exc):
    return None if exc is None else dict(type=type(exc).__name__, message=str(exc))


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


class DriverPreload:
    def __init__(self, factory, trace):
        self.factory, self.trace = factory, trace
        self.thread = None
        self.done = threading.Event()
        self.attempted = self.joined = False
        self.factory_calls = self.claims = 0
        self.value = self.error = self.cleanup_error = None
        self.started_ns = self.finished_ns = None

    def start(self):
        if self.attempted: raise RuntimeError('driver preload already attempted')
        self.trace.check('before_video_driver_preload')
        self.attempted = True
        self.thread = threading.Thread(target=self._run, name='joint-video-driver-preload', daemon=False)
        return self.trace.call('parallel_video_driver_launch', self.thread.start)

    def _run(self):
        self.started_ns = time.monotonic_ns()
        try:
            self.factory_calls += 1
            self.value = self.factory()
        except BaseException as exc: self.error = exc
        finally:
            self.finished_ns = time.monotonic_ns()
            self.done.set()

    def take(self):
        if not self.attempted or self.joined or self.claims:
            raise RuntimeError('driver preload not started, already claimed or disposed')
        self.trace.check('before_video_driver_ready')
        while not self.done.wait(.02): self.trace.check('waiting_for_video_driver_ready')
        self.thread.join()
        self.trace.check('after_video_driver_ready')
        if self.error is not None: raise self.error
        self.claims += 1
        return self.value

    def finish(self):
        if self.joined: return
        thread = self.thread
        if thread is not None:
            # enumerate also includes an in-flight Thread.start before ident is published.
            # Unknown launch completion is retained, never interpreted as safe disposal.
            while thread.ident is None and thread in threading.enumerate():
                try: self.done.wait(.05)
                except BaseException as exc: self.cleanup_error = self.cleanup_error or exc
            if thread.ident is not None:
                while not self.done.is_set():
                    try: self.done.wait(.05)
                    except BaseException as exc: self.cleanup_error = self.cleanup_error or exc
                while True:
                    try: thread.join(); break
                    except BaseException as exc: self.cleanup_error = self.cleanup_error or exc
        self.joined = True

    def report(self):
        bootstrap = [e for e in self.trace.events if e['phase'] == 'algorithm_bootstrap']
        begin = next((e['at_ns'] for e in bootstrap if e['kind'] == 'begin'), None)
        end = next((e['at_ns'] for e in bootstrap if e['kind'] in ('end', 'error')), None)
        overlap = (max(0, min(end, self.finished_ns)-max(begin, self.started_ns))
                   if None not in (begin, end, self.started_ns, self.finished_ns) else 0)
        alive = bool(self.thread and (self.thread.is_alive() or self.thread in threading.enumerate()))
        return dict(schema='v3b25_driver_preload_owner_v1', attempted=self.attempted,
            factory_calls=self.factory_calls, claims=self.claims,
            thread_joined=self.joined, thread_alive=alive,
            started_ns=self.started_ns, finished_ns=self.finished_ns, bootstrap_overlap_ns=overlap,
            error=describe(self.error), cleanup_error=describe(self.cleanup_error),
            lifecycle_complete=bool(self.joined and not alive and self.done.is_set()
                and self.factory_calls == self.claims == 1 and self.error is self.cleanup_error is None),
            startup_speed_improved_verified=False,
            scope='Owner-local original driver import only; no extra hardware owner or PS process')


@contextmanager
def install_runtime():
    if __package__:
        from . import joint_startup_worker as startup
        from .joint_startup import replace_attribute
    else:
        import joint_startup_worker as startup
        from joint_startup import replace_attribute
    instrument, finish = startup.instrument_binding, startup.finish_worker
    loaders = []
    def instrumented(binding, trace):
        binding = instrument(binding, trace)
        if loaders: raise RuntimeError('only one driver preload allowed')
        loader = DriverPreload(binding.api_factory, trace)
        loaders.append(loader)
        binding.driver_preload = loader
        binding.api_factory = lambda: trace.call('video_driver_ready_wait', loader.take)
        loader.start()
        return binding
    def finished(root, directory, binding, trace, failure, original):
        for loader in loaders: loader.finish()
        primary = None
        try: return finish(root, directory, binding, trace, failure, original)
        except BaseException as exc: primary = exc; raise
        finally:
            report = loaders[0].report() if loaders else dict(
                schema='v3b25_driver_preload_owner_v1', attempted=False, lifecycle_complete=False,
                thread_joined=True, thread_alive=False, factory_calls=0, claims=0,
                error=None, cleanup_error=None, bootstrap_overlap_ns=0)
            try: write_new(Path(directory) / 'owner_driver_preload.json', report)
            except BaseException as exc:
                if primary is None: raise
                print('保留原收尾错误；驱动预加载报告另有错误：' + str(exc), flush=True)
    with replace_attribute(startup, 'instrument_binding', instrumented), \
            replace_attribute(startup, 'finish_worker', finished):
        yield


def worker(base, directory, mailbox, stop, metrics_ready):
    if __package__:
        from .run_driver_preload import verify_candidate
        from .iic_handoff_worker import worker as previous
    else:
        from run_driver_preload import verify_candidate
        from iic_handoff_worker import worker as previous
    verify_candidate(Path(__file__).resolve().parent)
    with install_runtime(): previous(base, directory, mailbox, stop, metrics_ready)


def start_owner(context, base, directory, mailbox, stop, metrics_ready):
    child = context.Process(target=worker, args=(base, directory, mailbox, stop, metrics_ready),
        name='joint25-driver-preload-owner', daemon=False)
    child.start()
    return child
