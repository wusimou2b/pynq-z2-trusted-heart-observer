"""Cold PS target: unchanged reviewed main tail plus original import identity."""
if __package__:
    from .main_heart_process import ps_worker as main_worker
    from .lean_ps_worker import ReadyConnection
else:
    from main_heart_process import ps_worker as main_worker
    from lean_ps_worker import ReadyConnection


def ps_worker(connection,backend_source,*,root,source,host_check=False,run_id='main-spatial-short'):
    return main_worker(ReadyConnection(connection),backend_source,root=root,prepared_source=source,
                       host_check=host_check,run_id=run_id)
