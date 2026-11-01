"""Bounded same-call FIFO/MPU timing; no extra bus traffic or hot-path files."""
import ctypes as C
import threading
import time

STAGES={'fifo_call':1,'pointer_read':2,'data_read':3,'mpu_read':4}


class _Row(C.Structure):
    _fields_=[('kind',C.c_uint32),('call_id',C.c_uint32),('fifo_call_id',C.c_uint32),
        ('length',C.c_uint32),('begin',C.c_uint64),('end',C.c_uint64),
        ('cpu_begin',C.c_uint64),('cpu_end',C.c_uint64),('thread_id',C.c_uint64),
        ('error',C.c_uint32),('facts_valid',C.c_uint32),('wr',C.c_uint32),
        ('rd',C.c_uint32),('overflow',C.c_uint32),('available',C.c_uint32)]


class Trace:
    def __init__(self,*,capacity=8192,wall=time.monotonic_ns,cpu=time.thread_time_ns):
        if type(capacity)is not int or not 1<=capacity<=8192:raise ValueError('bounded FIFO trace required')
        self.buffer=(_Row*capacity)();self.capacity=capacity;self.count=0;self.wall=wall;self.cpu=cpu
        self.overflow=False;self.first_error=None;self.writer=None;self.current_fifo=self.last_fifo=0;self.instances=0
    def begin(self,stage,*,fifo_call_id=None,length=0):
        ident=threading.get_ident()
        if self.writer is None:self.writer=ident
        if self.writer!=ident:raise RuntimeError('unexpected second FIFO timing writer')
        if self.count==self.capacity:
            self.overflow=True;raise RuntimeError('FIFO timing capacity exceeded; no silent eviction')
        row=self.buffer[self.count];self.count+=1
        row.kind=STAGES[stage];row.call_id=self.count;row.thread_id=ident;row.length=length
        row.fifo_call_id=row.call_id if stage=='fifo_call' else self.current_fifo if fifo_call_id is None else fifo_call_id
        row.begin=self.wall();row.cpu_begin=self.cpu();return row
    def end(self,row,exc=None):
        row.cpu_end=self.cpu();row.end=self.wall();row.error=exc is not None
        if exc is not None and self.first_error is None:
            self.first_error=dict(stage={v:k for k,v in STAGES.items()}[row.kind],type=type(exc).__name__,message=str(exc))
    def report(self):
        names={v:k for k,v in STAGES.items()}
        records=[dict(stage=names[r.kind],call_id=r.call_id,fifo_call_id=r.fifo_call_id,length=r.length,
            begin_ns=r.begin,end_ns=r.end,thread_cpu_begin_ns=r.cpu_begin,thread_cpu_end_ns=r.cpu_end,
            wall_ns=r.end-r.begin if r.end else None,thread_cpu_ns=r.cpu_end-r.cpu_begin if r.end else None,
            thread_id=r.thread_id,error=bool(r.error),facts_valid=bool(r.facts_valid),wr=r.wr,rd=r.rd,
            overflow=r.overflow,available=r.available) for r in self.buffer[:self.count]]
        return dict(schema='original_fifo_call_timing_v1',records=records,capacity=self.capacity,
            allocated_bytes=C.sizeof(self.buffer),overflow=self.overflow,first_error=self.first_error,
            sensor_instances=self.instances,additional_iic_transactions=0,per_sample_ipc_added=0,hot_path_file_writes=0,
            current_ce_policy_unchanged=True,formal_observation_cap_seconds=5,
            clocks=dict(wall='monotonic_ns',cpu='observed_capture_thread_time_ns_not_PS_child'),
            scope='call brackets include scheduling; wall-minus-CPU is not proof of GIL/IPC; pointer bracket is not an exact hardware sample timestamp')


def observed_sensor(original,trace):
    class Observed(original):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);trace.instances+=1
        def read_fifo_ir_samples(self,*args,**kwargs):
            row=trace.begin('fifo_call');previous=trace.current_fifo;trace.current_fifo=row.call_id
            try:
                value=super().read_fifo_ir_samples(*args,**kwargs)
                row.wr=value.write_pointer;row.rd=value.read_pointer;row.overflow=value.overflow
                row.available=value.available;row.length=len(value.ir_samples);row.facts_valid=1
                return value
            except BaseException as exc:trace.end(row,exc);raise
            finally:
                if not row.end:trace.end(row)
                trace.current_fifo=previous;trace.last_fifo=row.call_id
        def read_registers(self,address,register,length):
            if address!=self.MAX_ADDRESS or not trace.current_fifo or not ((register==4 and length==3) or register==7):
                return super().read_registers(address,register,length)
            row=trace.begin('pointer_read' if register==4 else 'data_read',length=length)
            try:
                value=super().read_registers(address,register,length)
                if register==4 and len(value)==3:
                    row.wr=value[0]&31;row.overflow=value[1]&31;row.rd=value[2]&31
                    row.available=(row.wr-row.rd)%32 or (32 if row.overflow else 0);row.facts_valid=1
                return value
            except BaseException as exc:trace.end(row,exc);raise
            finally:
                if not row.end:trace.end(row)
        def read_acceleration_raw(self,*args,**kwargs):
            row=trace.begin('mpu_read',fifo_call_id=trace.last_fifo)
            try:return super().read_acceleration_raw(*args,**kwargs)
            except BaseException as exc:trace.end(row,exc);raise
            finally:
                if not row.end:trace.end(row)
    return Observed
