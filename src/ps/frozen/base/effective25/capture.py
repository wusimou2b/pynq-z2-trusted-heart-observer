"""25Hz FIFO output capture. Keep every consumed record, never clone IMU data."""
from heart_axi_live import pack_sample
from heart_v3a.live.capture import CaptureAdapter, phase_at
from heart_v3a.live.contracts import LiveBatch, LiveRecord
from .policy import PERIOD_US, ACCEL_REPEAT_LIMIT


def reconstruct_timestamps(size, read_us, previous_us):
    if size <= 0: return (),(), 'nominal_backprojection'
    nominal=tuple(read_us-(size-1-i)*PERIOD_US for i in range(size))
    if nominal[0] > previous_us: return nominal,nominal,'nominal_backprojection'
    interval=read_us-previous_us
    if interval < size: raise ValueError('timestamp interval cannot contain batch in strict order')
    stamps=tuple(previous_us+interval*(i+1)//size for i in range(size))
    return stamps,nominal,'compressed_observation_interval'


class Capture25(CaptureAdapter):
    """Frozen startup, terminal latch and post-stop diagnostics; new rate-dependent read."""
    def read_batch(self):
        if not self._begun or self._fault or self._capture_stopped:
            raise RuntimeError('采集未启动或已锁定停止')
        loop_started=self.clock.monotonic_ns()
        try:
            batch=self.sensors.read_fifo_ir_samples(timeout=.5)
        except Exception as exc:
            fault=self._make_fault('max30102_fifo_read','sensor_read_exception',0,exc,unknown=True)
            return LiveBatch(self._batch_id,(),self.clock.monotonic_ns(),fault)
        read_ns=self.clock.monotonic_ns()
        size=len(batch.ir_samples)
        if not 0 < size <= 32:
            fault=self._make_fault('max30102_fifo_read','invalid_fifo_batch_size',size)
            return LiveBatch(self._batch_id,(),read_ns,fault)
        axes=None
        valid=False
        try:
            axes=tuple(self.sensors.read_acceleration_raw())
            if len(axes)!=3 or any(type(v) is not int or not -32768<=v<=32767 for v in axes):
                raise ValueError('MPU加速度不是三路signed16整数')
            self._repeat_count=self._repeat_count+1 if axes==self._previous_acceleration else 1
            self._previous_acceleration=axes
            if axes==(0,0,0): self._make_fault('mpu_acceleration_read','acceleration_all_zero',size)
            elif self._repeat_count>=ACCEL_REPEAT_LIMIT:
                self._make_fault('mpu_acceleration_read','acceleration_repeated_suspected_stale',size)
            else: valid=True
        except Exception as exc:
            self._make_fault('mpu_acceleration_read','sensor_read_exception',size,exc)
        mpu_ns=self.clock.monotonic_ns()
        if batch.overflow: self._make_fault('max30102_fifo_read','max30102_overflow',size)
        if self._sequence+size-1 > 0xFFFFFFFF:
            self._make_fault('sequence','sequence_range_exhausted',size)
        try:
            stamps,nominal,policy=reconstruct_timestamps(size,read_ns//1000,self._previous_timestamp_us)
        except ValueError as exc:
            stamps,nominal,policy=('',)*size,('',)*size,'invalid_observation_interval'
            self._make_fault('timestamp_reconstruction','timestamp_reconstruction_error',size,exc)
        loopback=''
        if valid and self._fault is None:
            packet=pack_sample(self._sequence+size-1,stamps[-1],int(batch.ir_samples[-1]),*axes)
            try:
                loopback=self.fifo.round_trip(packet)==packet
                if not loopback: self._make_fault('axi_fifo_loopback','pl_fifo_error',size)
            except Exception as exc:
                loopback=False
                self._make_fault('axi_fifo_loopback','pl_fifo_error',size,exc)
        loop_ns=self.clock.monotonic_ns()-loop_started
        records=[]
        for i,ir in enumerate(batch.ir_samples):
            newest=i==size-1
            paired=newest and valid
            g=tuple(v/16384 for v in axes) if paired else ('','','')
            relative=(stamps[i]-self.started_ns//1000)/1e6 if stamps[i]!='' else ''
            phase,index,elapsed=phase_at(self.protocol,relative) if relative!='' else ('','','')
            raw_axes=axes if newest and axes is not None and len(axes)==3 else ('','','')
            row=dict(sequence=self._sequence,timestamp_us=stamps[i],read_timestamp_us=read_ns//1000,
                nominal_timestamp_us=nominal[i],timestamp_policy=policy,time_s=relative,
                ir_raw=int(ir),ax_g=g[0],ay_g=g[1],az_g=g[2],pair_ok=paired,accel_valid=paired,
                mpu_ax_raw=raw_axes[0],mpu_ay_raw=raw_axes[1],mpu_az_raw=raw_axes[2],
                accel_repeat_count=self._repeat_count if newest else '',fifo_batch_size=size,
                max30102_overflow=int(batch.overflow),pl_fifo_ok=loopback if newest else '',
                error=self._fault.reason if self._fault else '',phase=phase,phase_index=index,
                phase_elapsed_s=elapsed,batch_id=self._batch_id,max_write_pointer=int(batch.write_pointer),
                max_read_pointer=int(batch.read_pointer),max_available=int(batch.available),
                ppg_read_completed_ns=read_ns,mpu_read_completed_ns=mpu_ns,capture_loop_ns=loop_ns)
            records.append(LiveRecord(row,read_ns)); self._sequence+=1
        if stamps[-1]!='': self._previous_timestamp_us=stamps[-1]
        result=LiveBatch(self._batch_id,tuple(records),self.clock.monotonic_ns(),self._fault)
        self._batch_id+=1
        return result
