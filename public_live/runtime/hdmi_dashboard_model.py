"""Owner-local, read-only presentation; never computes or grants a heart result."""
import math
from numbers import Real
import threading

FIELDS=('raw','mean','nlms_candidate','joint_output')
ROUTES={'raw':'RAW','mean':'MEAN25','nlms':'JOINT','none':'NONE',None:'NONE'}


def number(value):
    return isinstance(value,Real) and not isinstance(value,bool) and math.isfinite(value)


class DashboardModel:
    def __init__(self):
        self._lock=threading.Lock()
        self._snapshot=self._published=self._motion=None
        self._observations=0

    def observe(self,snapshot,*,published_ns):
        with self._lock:
            self._snapshot,self._published=snapshot,published_ns
            self._observations+=1

    def motion(self,decision):
        with self._lock:self._motion=decision

    def panel(self,now_ns,*,curves=True):
        with self._lock:snapshot,published,motion=self._snapshot,self._published,self._motion
        p=dict(bpm_text='N/A',state='PREPARING',route='NONE',quality='UNKNOWN',contact=False,mix=None,
            sequence=None,read_ns=None,checked_ns=now_ns,generation=None,status_age_ns=None,result_age_ns=None,
            eligible=False,historical=True,span_seconds=5.,rows=(),motion=motion,
            plot_start=None,plot_end=None,curve_count=4)
        if snapshot is None:return p
        latest=snapshot.latest
        status_age=now_ns-published
        status_fresh=0<=status_age<=100_000_000
        p.update(status_age_ns=status_age,state='WAIT' if status_fresh else 'STALE')
        if snapshot.state!='running':p['state']=snapshot.state.upper()
        if snapshot.fault is not None:p['state']='FAULT'
        if latest is not None:
            frame=latest.runtime.frame;safety=snapshot.counts.get('raw_safety',{})
            age=now_ns-latest.saved.record.read_completed_ns
            current=bool(snapshot.state=='running' and snapshot.fault is None and status_fresh and 0<=age<=1_000_000_000)
            permitted=bool(current and safety.get('contact_ready') is True
                and latest.slot.generation==safety.get('generation') and frame.output_allowed
                and number(frame.bpm) and frame.bpm>0)
            p.update(sequence=frame.sequence,read_ns=latest.saved.record.read_completed_ns,result_age_ns=age,
                generation=safety.get('generation'),historical=not current,eligible=permitted,
                route=ROUTES.get(frame.selected_route,'UNKNOWN') if current else 'STALE',
                quality=str(frame.selected_quality or 'UNKNOWN').upper() if current else 'UNKNOWN',
                contact=safety.get('contact_ready') is True if current else False,
                mix=frame.nlms_mix if number(frame.nlms_mix) else None)
            if not 0<=age<=1_000_000_000 and p['state'] in ('WAIT','LIVE'):p['state']='STALE'
            if permitted:
                p.update(bpm_text=format(frame.bpm,'.1f'),state='LIVE',
                    span_seconds=float(min(20.,max(1.,360./frame.bpm))))
        if not curves or not snapshot.history:return p
        end=snapshot.history[-1].runtime.frame.time_s
        if not number(end):return p
        start=end-p['span_seconds'];rows=[]
        for item in reversed(snapshot.history[-500:]):
            f=item.runtime.frame
            if not number(f.time_s):continue
            if f.time_s<start-1e-9:break
            rows.append((f.sequence,float(f.time_s),*(float(v) if number(v) else None
                for v in (getattr(f,key) for key in FIELDS))))
        p.update(rows=tuple(reversed(rows)),plot_start=start,plot_end=end)
        return p

    def report(self):
        with self._lock:count=self._observations
        return dict(observations=count,history_capacity=500,history_copies_on_observe=0,
            status_max_age_ns=100_000_000,result_max_age_ns=1_000_000_000,
            algorithm_changed=False,extra_sensor_reads=0,extra_ps_ipc_messages=0)
