"""Bounded scalar projection for video; never sends curves or image buffers."""
import json
from types import SimpleNamespace as N

FRAME_FIELDS=('sequence','valid','motion_ready','motion','motion_rms_g','bpm',
              'output_allowed','selected_route','selected_quality','nlms_mix')
RAW_FIELDS=('sequence','pair_ok','accel_valid','mpu_read_completed_ns')
PACKET_BYTES=4096


def project(snapshot,published_ns,imu_observed_ns=None):
    if type(published_ns) is not int or published_ns<0:raise ValueError('invalid publication clock')
    latest=snapshot.latest
    row=None if latest is None else dict(
        raw={k:latest.saved.record.raw[k] for k in RAW_FIELDS},
        read_ns=latest.saved.record.read_completed_ns,
        finished_ns=latest.processing_finished_ns,epoch=latest.runtime.pl_epoch,
        generation=latest.slot.generation,frame={k:getattr(latest.runtime.frame,k) for k in FRAME_FIELDS})
    imu_observed_ns=published_ns if imu_observed_ns is None else imu_observed_ns
    if type(imu_observed_ns) is not int or imu_observed_ns<0:raise ValueError('invalid IMU observation clock')
    return dict(state=snapshot.state,fault=None if snapshot.fault is None else True,
                safety=dict(snapshot.counts.get('raw_safety',{})),latest=row,published_ns=published_ns,
                imu_observed_ns=imu_observed_ns)


def restore(packet):
    row=packet['latest'];latest=None
    if row is not None:
        if set(row['raw'])!=set(RAW_FIELDS) or set(row['frame'])!=set(FRAME_FIELDS):
            raise ValueError('video projection field contract differs')
        latest=N(saved=N(record=N(raw=row['raw'],read_completed_ns=row['read_ns'])),
            runtime=N(frame=N(**row['frame']),pl_epoch=row['epoch']),slot=N(generation=row['generation']),
            processing_finished_ns=row['finished_ns'])
    return N(state=packet['state'],fault=packet['fault'],latest=latest,history=(),counts={'raw_safety':packet['safety']})


def imu_key(row):
    if row is None:return None,None
    f=row['frame']
    payload=dict(raw=row['raw'],epoch=row['epoch'],finished_ns=row['finished_ns'],
        frame={k:f[k] for k in ('sequence','valid','motion_ready','motion','motion_rms_g')})
    return (row['epoch'],f['sequence']),json.dumps(payload,sort_keys=True,allow_nan=False)


class StateChannel:
    def __init__(self,ctx,run_epoch,manifest_sha256,*,capacity=64):
        if not isinstance(run_epoch,str) or not run_epoch or len(manifest_sha256)!=64:
            raise ValueError('video state identity missing')
        if type(capacity) is not int or not 1<=capacity<=64:raise ValueError('invalid bounded capacity')
        self.run_epoch,self.manifest_sha256,self.capacity=run_epoch,manifest_sha256,capacity
        self.lock=ctx.Lock();self.ring=ctx.RawArray('B',capacity*PACKET_BYTES)
        self.lengths=ctx.RawArray('I',capacity);self.latest=ctx.RawArray('B',PACKET_BYTES)
        self.latest_length=ctx.RawValue('I',0);self.head=ctx.RawValue('Q',0);self.tail=ctx.RawValue('Q',0)
        self._previous=self._payload=None

    def _encode(self,packet):
        data=json.dumps(dict(schema=1,run_epoch=self.run_epoch,manifest_sha256=self.manifest_sha256,
                             packet=packet),allow_nan=False,separators=(',',':')).encode('utf-8')
        if len(data)>PACKET_BYTES:raise BufferError('video scalar packet exceeds fixed capacity')
        return data

    def _decode(self,data):
        envelope=json.loads(data)
        if (envelope['schema'],envelope['run_epoch'],envelope['manifest_sha256'])!=(1,self.run_epoch,self.manifest_sha256):
            raise ValueError('video state identity mismatch')
        return envelope['packet']

    def publish(self,snapshot,*,published_ns,imu_observed_ns=None):
        packet=project(snapshot,published_ns,imu_observed_ns);key,payload=imu_key(packet['latest'])
        if key is not None and key==self._previous and payload!=self._payload:
            raise ValueError('IMU duplicate identity payload changed')
        append=key is not None and key!=self._previous
        data=self._encode(packet)
        if not self.lock.acquire(timeout=.05):raise TimeoutError('video state writer lock50ms')
        try:
            if append and self.head.value-self.tail.value>=self.capacity:
                raise BufferError('video IMU evidence channel full; no overwrite')
            if append:
                slot=self.head.value%self.capacity;start=slot*PACKET_BYTES
                memoryview(self.ring).cast('B')[start:start+len(data)]=data
                self.lengths[slot]=len(data);self.head.value+=1
            memoryview(self.latest).cast('B')[:len(data)]=data;self.latest_length.value=len(data)
        finally:self.lock.release()
        if key is not None:self._previous,self._payload=key,payload

    def consume(self):
        if not self.lock.acquire(timeout=.05):raise TimeoutError('video state reader lock50ms')
        try:
            rows=[];tail=self.tail.value
            for index in range(tail,self.head.value):
                slot=index%self.capacity;start=slot*PACKET_BYTES;n=self.lengths[slot]
                rows.append(bytes(memoryview(self.ring).cast('B')[start:start+n]))
            data=bytes(memoryview(self.latest).cast('B')[:self.latest_length.value])
            # Validate before committing consumption: bad identity cannot erase a barrier.
            decoded=[self._decode(x) for x in rows];last=self._decode(data) if data else None
            self.tail.value=self.head.value
        finally:self.lock.release()
        return ([(restore(p).latest,p['imu_observed_ns']) for p in decoded],
                restore(last) if last else None,last['published_ns'] if last else None)


class Consumer:
    def __init__(self,channel,model,fusion):self.channel,self.model,self.fusion=channel,model,fusion
    def sync(self):
        rows,snapshot,published=self.channel.consume()
        for record,observed in rows:self.fusion.observe(record,observed_ns=observed)
        if snapshot is not None:self.model.observe(snapshot,published_ns=published)


class RemoteModel:
    def __init__(self,consumer):self.consumer=consumer
    def panel(self,*a,**k):self.consumer.sync();return self.consumer.model.panel(*a,**k)
