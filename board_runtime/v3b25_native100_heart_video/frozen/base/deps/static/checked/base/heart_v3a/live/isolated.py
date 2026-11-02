"""独立小试会话；默认实时入口不切换到这里。"""
from .process_chain import ProcessChain
from .session import LiveSession


class IsolatedLiveSession(LiveSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._process_chain = None

    def start(self):
        with self._lock:
            if self._started_once or self._state != 'created':
                raise RuntimeError('会话只能启动一次')
            self._claim_owner()
        try:
            # 冷启动不挤占原3秒实时启动预算；此时尚未启动正式采集线程。
            self._process_chain = ProcessChain(self.backend.source)
        except BaseException as exc:
            self._fail('process_preflight', str(exc))
            self.stop()
            raise
        try:
            return super().start()
        except BaseException as exc:
            self._fail('startup', str(exc))
            self.stop()
            raise

    def stop(self, *, display_metrics=None):
        if not self._threads and self._process_chain is not None:
            self._close_processing_chain()
        return super().stop(display_metrics=display_metrics)

    def _create_processing_chain(self, measured):
        self._process_chain.attach_backend(measured)
        return self._process_chain

    def _close_processing_chain(self):
        if self._process_chain is not None:
            try:
                self._process_chain.close()
            finally:
                # 如OS仍未结束子进程，保留处理线程/所有权，原stop返回shutdown_incomplete。
                while self._process_chain._worker.is_alive():
                    self._process_chain._worker.join(.05)
            info = self._process_chain.info()
            if info['forced_termination'] or info['exitcode'] != 0:
                self._fail('processing_cleanup', 'PS子进程未自然退出', details=info)

    def _make_summary(self, cleanup_complete, display_metrics=None):
        summary = super()._make_summary(cleanup_complete, display_metrics)
        summary['isolation'] = self._process_chain.info() if self._process_chain else dict(
            strategy='spawn_ps_parent_hardware', worker_started=False, cleanup_complete=True)
        return summary
