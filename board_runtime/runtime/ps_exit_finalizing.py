"""One bounded finalizing-state slot per original child exit event."""
import multiprocessing as mp
import sys
from types import BuiltinFunctionType

CAPACITY=64


def make_shared():
    ctx=mp.get_context('spawn')
    return dict(states=ctx.RawArray('b',[-1]*CAPACITY),count=ctx.RawValue('i',0),
        errors=ctx.RawValue('i',0),pid=ctx.RawValue('q',0))


def attach(trace,state):
    """Only this fresh child's trace instance changes; callbacks stay original."""
    original=trace.event;query=sys.is_finalizing;ident=trace.ident;main=trace.main_ident
    table=trace.data;count=state['count'];errors=state['errors'];slots=state['states']
    state['pid'].value=table['pid'].value
    capacity=len(slots)
    def failed(_Base=BaseException):
        try:errors.value+=1
        except _Base:pass
    def event(name,detail=0,_Base=BaseException):
        if ident()!=main:return original(name,detail)
        before=table['count'].value;value=-1
        try:
            result=query()
            if result is True:value=1
            elif result is False:value=0
            else:failed()
        except _Base:failed()
        result=original(name,detail)
        try:
            after=table['count'].value
            if after==before+1 and 0<=before<capacity:
                slots[before]=value;count.value=after
        except _Base:failed()
        return result
    trace.event=event
    return trace


def snapshot(state,child):
    """Only after original owner/PS exit proof; never query live writers here."""
    issues=[];count=state['count'].value;pid=state['pid'].value;rows=child['rows']
    if pid!=child['pid']:issues.append('state PID differs from exited PS')
    if count!=len(rows) or not 0<=count<=CAPACITY:issues.append('state/event count differs')
    result=[]
    for index,row in enumerate(rows[:CAPACITY]):
        value=state['states'][index]
        known=index<count and value in (0,1)
        if not known:issues.append('unknown state at event '+str(index))
        result.append(dict(index=index,event=row['event'],at_ns=row['at_ns'],detail=row['detail'],
            is_finalizing=bool(value) if known else None))
    errors=state['errors'].value
    if errors:issues.append('state query/storage errors')
    return dict(pid=pid,count=count,capacity=CAPACITY,errors=errors,issues=issues,
        complete=bool(rows and not issues),rows=result,
        finalizing_seen=any(r['is_finalizing'] is True for r in result),
        scope='Observed interpreter state; not module-cleanup completion or OS exit')


def verify_query():
    query=sys.is_finalizing
    if not (isinstance(query,BuiltinFunctionType) and query.__module__=='sys' and query.__name__=='is_finalizing'):
        raise ValueError('actual sys.is_finalizing builtin required')
    if query() is not False:raise ValueError('runtime already finalizing or query invalid')
    return dict(module=query.__module__,name=query.__name__,python=sys.version,
        reference_cpython_version='3.10.4',reference_order_is_binary_proof=False)
