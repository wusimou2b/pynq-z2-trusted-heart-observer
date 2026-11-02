"""Cold, reversible installation before retained child copy adaptation."""
from contextlib import contextmanager


@contextmanager
def installed():
    import main_tail_compact
    from joint_startup import replace_attribute
    from route_recovery import wrap_factory
    with replace_attribute(main_tail_compact,'make_chain',wrap_factory(main_tail_compact.make_chain)):
        yield


class Ready:
    def __init__(self,pipe):self.pipe=pipe
    def __getattr__(self,key):return getattr(self.pipe,key)
    def send(self,message):
        if message[:2]==(0,'ready'):
            from route_recovery import TAG
            message=(0,'ready',dict(message[2],route_output_policy=TAG))
        return self.pipe.send(message)
