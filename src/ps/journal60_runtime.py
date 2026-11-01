"""One candidate scope around the preserved owner, PS and lifecycle."""
from contextlib import ExitStack,contextmanager
from functools import partial
import json
from pathlib import Path

if __package__:
    from .journal60_guard import verify,SOURCE_SHA
    from .native40_boundary import Native40Main,Native40Snapshot
    from .heart_video_journal import JournalAdapter
else:
    from journal60_guard import verify,SOURCE_SHA
    from native40_boundary import Native40Main,Native40Snapshot
    from heart_video_journal import JournalAdapter

@contextmanager
def replaced(module,name,value):
    before=getattr(module,name);setattr(module,name,value)
    try:yield
    finally:setattr(module,name,before)

def verified_ps_worker(connection,backend_source,*,root,expected_journal_manifest_sha256,
                       expected_schedule_manifest_sha256,**kwargs):
    if expected_schedule_manifest_sha256!=SOURCE_SHA:raise ValueError('retained schedule identity differs')
    verify(root,expected_journal_manifest_sha256)
    from owner_schedule_runtime import verified_ps_worker as original
    class ReadyConnection:
        def send(self,message):
            if message[:2]==(0,'ready'):
                message=(0,'ready',dict(message[2],journal60_ps=dict(
                    manifest_sha256=expected_journal_manifest_sha256,manifest_verified_before_original=True)))
            return connection.send(message)
        def __getattr__(self,name):return getattr(connection,name)
    return original(ReadyConnection(),backend_source,root=root,
        expected_schedule_manifest_sha256=SOURCE_SHA,**kwargs)

def worker(*args,root,expected_journal_manifest_sha256,expected_schedule_manifest_sha256,**kwargs):
    if expected_schedule_manifest_sha256!=SOURCE_SHA:raise ValueError('retained schedule identity differs')
    verify(root,expected_journal_manifest_sha256)
    import owner_schedule_runtime as original,sample40_runtime as native,status60_ab_runtime as ab
    old=(native.Sample40Main,native.Sample40Snapshot,original.verified_ps_worker,ab.Activation.bind)
    adapters=[];failure=None
    def bind(registry,session):
        old[3](registry,session)
        from heart_v2.runtime_main_chain import RuntimeFrame
        from heart_v3a.runtime_pl_chain import PlRuntimeFrame
        adapter=JournalAdapter();adapters.append(adapter)
        registry.stack.callback(adapter.restore)
        adapter.install(session._journal,RuntimeFrame,PlRuntimeFrame)
    try:
        with ExitStack() as stack:
            stack.enter_context(replaced(native,'Sample40Main',Native40Main))
            stack.enter_context(replaced(native,'Sample40Snapshot',Native40Snapshot))
            stack.enter_context(replaced(ab.Activation,'bind',bind))
            stack.enter_context(replaced(original,'verified_ps_worker',partial(verified_ps_worker,
                expected_journal_manifest_sha256=expected_journal_manifest_sha256)))
            return original.worker(*args,root=root,expected_schedule_manifest_sha256=SOURCE_SHA,**kwargs)
    except BaseException as exc:failure=exc;raise
    finally:
        report=dict(schema='owner_journal60_v1',native40_python_step1=True,scalar_journal_conversion=True,journal_adapters=[a.report() for a in adapters],
            original_algorithm=True,original_ipc=True,automatic_retry=False,
            manifest_sha256=expected_journal_manifest_sha256,
            adapters_restored=old==(native.Sample40Main,native.Sample40Snapshot,original.verified_ps_worker,ab.Activation.bind),
            original_error=None if failure is None else dict(type=type(failure).__name__,message=str(failure)))
        directory=Path(args[1])
        if directory.is_dir():
            try:
                with (directory/'journal60-owner.json').open('x',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
            except BaseException as exc:
                if failure is not None:raise failure from exc
                raise

def start_owner(context,*args,root,expected_journal_manifest_sha256,expected_schedule_manifest_sha256,**kwargs):
    if Path(root).resolve()!=Path(__file__).resolve().parent:raise ValueError('journal owner root differs')
    verify(root,expected_journal_manifest_sha256)
    process=context.Process(target=partial(worker,root=root,expected_journal_manifest_sha256=expected_journal_manifest_sha256,
        expected_schedule_manifest_sha256=expected_schedule_manifest_sha256,**kwargs),args=args,
        name='joint25-native40-journal60-owner',daemon=False)
    process.start();return process
