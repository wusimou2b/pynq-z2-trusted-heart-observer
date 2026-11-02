"""Original C enforces SAMPLE40; Python return keeps the outer step deadline."""
if __package__:
    from .sample40_runtime import Sample40Main,Sample40Snapshot
else:
    from sample40_runtime import Sample40Main,Sample40Snapshot


class Native40Snapshot(Sample40Snapshot):
    def transact(self,deadline,valid):
        self.native_success=False
        # Original implementation accepts only rc=0 AND phase=7. In particular,
        # a C expiry after ACK with phase=7 must never count as a success.
        result=super().transact(deadline,valid)
        self.native_success=True
        self.native_successful_transactions=getattr(self,'native_successful_transactions',0)+1
        return result


class Native40Main(Sample40Main):
    def initialize_metrics(self):
        super().initialize_metrics()
        self._python_over40=0;self._python_return_max_ns=0

    def _begin(self):
        if self._sample40_active:
            if not isinstance(self.reader,Native40Snapshot):
                raise RuntimeError('native40 requires the validated native receipt adapter')
            self.reader.native_success=False
        return super()._begin()

    def _time(self):
        if not self._sample40_active or not getattr(self.reader,'native_success',False):
            return super()._time()
        now=self.clock()  # Reuse the original post-native clock call.
        outer=self.deadline if self.deadline is not None else self.started+1.
        if now>=outer:
            if self._failure40 is None:
                self._failure40=dict(origin='python_step_return',native_success=True,
                    started=self.started,native_deadline=self.active_deadline,
                    original_step_deadline=outer,guard_checked_now=now,
                    elapsed_seconds=now-self.started)
            raise TimeoutError('original step deadline expired after native SAMPLE success; no retry')
        return now

    def observe(self,result):
        super().observe(result)
        ns=round(result.transaction_seconds*1_000_000_000)
        self._python_over40+=int(ns>=40_000_000)
        self._python_return_max_ns=max(self._python_return_max_ns,ns)

    def audit(self):
        result=super().audit()
        result.update(schema='native40_python_step1_v1',
            native_successful_transactions=getattr(self.reader,'native_successful_transactions',0),
            native_deadline_seconds=.040,python_default_step_seconds=1.,
            python_return_over40=self._python_over40,
            max_python_return_ns=self._python_return_max_ns,
            native_duration_measured=False,
            transaction_duration_scope='Python start-to-return wall including handoff, not C duration',
            protection_scope_changed=True,
            scope='Original C checks the same absolute deadline through ACK; software return is checked against the original outer step. No retry.')
        return result
