"""Same owner snapshot bytecode; specialize copying of five immutable scalars.

No state cache: both original safety observations and every lock/guard remain.
Unknown records/count layouts keep the original recursive copying behavior.
Only the owner's private projection closure is changed, never a shared class.
"""
from contextlib import contextmanager
from dataclasses import asdict, fields
from functools import lru_cache, partial
import hashlib
import inspect
from types import FunctionType, MappingProxyType

SAFETY_FIELDS=('generation','contact_ready','raw_observed','latest_read_ns','fault')
SNAPSHOT_FIELDS=('state','fault','latest','history','counts')
POST_INIT_SHA='27ab2a6d35954d38c21a28eed90b6023e2d45847f637c9d350e229c9e3ae4371'


@lru_cache(maxsize=4)
def qualified(snapshot_type,safety_type):
    return (tuple(f.name for f in fields(snapshot_type))==SNAPSHOT_FIELDS
        and tuple(f.name for f in fields(safety_type))==SAFETY_FIELDS
        and snapshot_type.__dataclass_params__.frozen
        and snapshot_type.__new__ is object.__new__
        and not hasattr(snapshot_type,'__slots__')
        and hashlib.sha256(inspect.getsource(snapshot_type.__post_init__).encode()).hexdigest()==POST_INIT_SHA)


def flat_safety(row):
    return (type(row) is dict and len(row)==5
        and type(row.get('generation')) is int
        and type(row.get('contact_ready')) is bool
        and type(row.get('raw_observed')) is int
        and ('latest_read_ns' in row and (row['latest_read_ns'] is None or type(row['latest_read_ns']) is int))
        and type(row.get('fault')) is str)


class FlatSnapshot:
    def __init__(self,snapshot_type,safety_type):
        self.snapshot_type,self.safety_type=snapshot_type,safety_type
        self.qualified=qualified(snapshot_type,safety_type)
        self.fast_safety=self.fast_snapshot=self.fallback_safety=self.fallback_snapshot=0

    def safety_dict(self,state):
        if self.qualified and type(state) is self.safety_type:
            row=dict(generation=state.generation,contact_ready=state.contact_ready,
                raw_observed=state.raw_observed,latest_read_ns=state.latest_read_ns,fault=state.fault)
            if flat_safety(row):
                self.fast_safety+=1
                return row
        self.fallback_safety+=1
        return asdict(state)

    def snapshot(self,state,fault,latest,history,counts):
        if (self.qualified and type(history) is tuple and type(counts) is dict
                and len(counts)==1 and flat_safety(counts.get('raw_safety'))):
            # Replicate precisely the pinned __post_init__ result. Both dicts
            # are private copies; mutable caller state cannot leak through.
            frozen=MappingProxyType({'raw_safety':MappingProxyType(dict(counts['raw_safety']))})
            result=object.__new__(self.snapshot_type)
            result.__dict__.update(state=state,fault=fault,latest=latest,history=history,counts=frozen)
            self.fast_snapshot+=1
            return result
        self.fallback_snapshot+=1
        return self.snapshot_type(state,fault,latest,history,counts)

    def report(self):
        return dict(fast_safety=self.fast_safety,fast_snapshot=self.fast_snapshot,
            fallback_safety=self.fallback_safety,fallback_snapshot=self.fallback_snapshot,
            original_snapshot_bytecode=True,original_safety_read_count=True,no_state_cache=True)


def _cell(value):
    return (lambda:value).__closure__[0]


@contextmanager
def publication_projection(session,*,_retained=None):
    if _retained is None:
        from owner_publish_projection import publication_projection as retained
    else:
        retained=_retained
    from heart_v3a.live.contracts import LiveSnapshot
    from v3a_25hz_live.safety import SafetyState
    adapter=FlatSnapshot(LiveSnapshot,SafetyState)
    with retained(session):
        original=session.snapshot
        namespace=dict(original.__globals__)
        if namespace.get('asdict') is not asdict:raise ValueError('original snapshot copying differs')
        namespace['asdict']=adapter.safety_dict
        cells=dict(zip(original.__code__.co_freevars,original.__closure__))
        if cells['LiveSnapshot'].cell_contents is not LiveSnapshot:raise ValueError('original snapshot class differs')
        cells['LiveSnapshot']=_cell(adapter.snapshot)
        candidate=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,
            tuple(cells[name] for name in original.__code__.co_freevars))
        candidate.__kwdefaults__=original.__kwdefaults__
        session.snapshot=candidate
        try:yield adapter
        finally:
            if session.snapshot is candidate:session.snapshot=original


@contextmanager
def installed():
    """Apply before the retained owner installs its SnapshotAdapter scopes."""
    import owner_publish_projection
    original=owner_publish_projection.publication_projection
    wrapper=partial(publication_projection,_retained=original)
    owner_publish_projection.publication_projection=wrapper
    try:yield
    finally:
        if owner_publish_projection.publication_projection is wrapper:
            owner_publish_projection.publication_projection=original
