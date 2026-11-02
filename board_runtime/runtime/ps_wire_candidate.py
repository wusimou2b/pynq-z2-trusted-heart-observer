"""Tuple-state transport plus deferred offline import in a fresh PS child."""
from functools import partial
import sys


class Ready:
    def __init__(self,pipe,placement):self.pipe,self.placement=pipe,placement
    def __getattr__(self,name):return getattr(self.pipe,name)
    def send(self,message):
        if message[:2]==(0,'ready'):
            message=(0,'ready',dict(message[2],tuple_wire='same_objects_positional_v1',
                ps_cpu_placement=self.placement,pandas_loaded_at_ready='pandas' in sys.modules))
        return self.pipe.send(message)


def wrap_connection(pipe,placement):
    from ps_tuple_wire import Connection
    return Ready(Connection(pipe),placement)


def target(pipe,source,*,delegate,host_check=False,pin_cpu=False,**kwargs):
    # The fixed-core full-load candidate regressed; inherited OS placement is
    # the default. Keep an explicit opt-in for reproducing that saved variant.
    if pin_cpu and not host_check:
        from ps_core_placement import pin
        placement=pin('ps')
    else:
        placement=dict(role='ps',host_only=host_check,affinity_changed=False)
    return delegate(wrap_connection(pipe,placement),source,**kwargs)


def Bridge(source,delegate,*,run_id,host_check=False,pin_cpu=False):
    from main_rpc_compact import Bridge as original
    from ps_tuple_wire import Connection
    bridge=original(source,partial(target,delegate=delegate,host_check=host_check,pin_cpu=pin_cpu),run_id=run_id)
    if bridge._ready.get('tuple_wire')!='same_objects_positional_v1':
        bridge._fault='tuple wire READY differs';bridge.close();raise RuntimeError(bridge._fault)
    bridge._connection=Connection(bridge._connection)
    return bridge
