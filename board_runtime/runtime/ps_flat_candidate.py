"""Single-roundtrip Pipe candidate; original process and exit policies intact."""
from functools import partial


class Ready:
    def __init__(self, connection): self.connection = connection
    def __getattr__(self, name): return getattr(self.connection, name)
    def send(self, message):
        if message[:2] == (0, 'ready'):
            message = (0, 'ready', dict(message[2], flat_wire='v3b25_same_records_flat_v1',
                                      ps_cpu_placement=dict(affinity_changed=False)))
        return self.connection.send(message)


def target(pipe, source, *, delegate):
    from ps_flat_wire import Connection
    return delegate(Ready(Connection(pipe)), source)


def Bridge(source, delegate, *, run_id):
    from main_rpc_compact import Bridge as original
    from ps_flat_wire import Connection, TAG
    bridge = original(source, partial(target, delegate=delegate), run_id=run_id)
    if bridge._ready.get('flat_wire') != TAG:
        bridge._fault = 'flat wire READY identity differs'
        bridge.close()
        raise RuntimeError(bridge._fault)
    bridge._connection = Connection(bridge._connection)
    return bridge
