"""Connect the already-qualified flat codec to the retained LIVE bridge factory.

The outer owner scope still installs its original close observer. Both endpoints
are selected by ps_flat_candidate; the child retains the original verified entry.
No sensor, timing, algorithm, queue or process-lifecycle policy changes here.
"""
from contextlib import contextmanager


@contextmanager
def installed():
    import ps_wire_candidate
    from ps_flat_candidate import Bridge
    from joint_startup import replace_attribute
    # lean_joint_runtime imports this attribute when ENTERING its scope. Enter
    # this scope first; patching main_heart_process earlier gets overwritten.
    with replace_attribute(ps_wire_candidate, 'Bridge', Bridge):
        yield


def require_installed(bridge):
    from ps_flat_wire import Connection, TAG
    if (type(bridge._connection) is not Connection or
            bridge._ready.get('flat_wire') != TAG or
            'tuple_wire' in bridge._ready):
        raise RuntimeError('live flat codec not installed at both endpoints')
    if bridge._ready.get('ps_cpu_placement', {}).get('affinity_changed') is not False:
        raise RuntimeError('original free CPU scheduling required')
