"""Live PL-only candidate with bounded, post-cleanup numerical spot checks."""
import hashlib
import time

import numpy as np

if __package__:
    from .joint_video_runtime import VideoResources,STAT_FIELDS
    from .joint_video_transport import validate_frame
else:
    from joint_video_runtime import VideoResources,STAT_FIELDS
    from joint_video_transport import validate_frame

TRANSPORT_PARTS=('pack_bgr','zero_x','flush','mmio_read','mmio_write','wait_sleep','other')


class _TimedIO:
    def __init__(self,raw,measure):self.raw,self.measure=raw,measure
    def read(self,*args,**kwargs):return self.measure('mmio_read',lambda:self.raw.read(*args,**kwargs))
    def write(self,*args,**kwargs):return self.measure('mmio_write',lambda:self.raw.write(*args,**kwargs))


class _TimedBuffer:
    def __init__(self,raw,measure):self.raw,self.measure=raw,measure
    def __setitem__(self,index,value):
        if index==(Ellipsis,slice(None,3)):name='pack_bgr'
        elif index==(Ellipsis,3):name='zero_x'
        else:raise RuntimeError('original finite buffer packing contract changed')
        self.measure(name,lambda:self.raw.__setitem__(index,value))
    def flush(self):return self.measure('flush',self.raw.flush)


class MeasuredPort:
    """Time original operations, with no extra MMIO action or protocol change."""
    def __init__(self,port,*,clock_ns=time.monotonic_ns):
        self.port,self.clock_ns=port,clock_ns
        self.last_timing=None;self.busy=False
    @property
    def completed(self):return self.port.completed

    def process(self,*args,**kwargs):
        if self.busy:raise RuntimeError('one finite video transfer at a time')
        self.busy=True;p=self.port
        originals={k:getattr(p,k) for k in ('buffer','core','dma','gpio','sleep')}
        ns=dict.fromkeys(TRANSPORT_PARTS,0);calls=dict.fromkeys(TRANSPORT_PARTS[:-1],0)
        def measure(name,operation):
            started=self.clock_ns()
            try:return operation()
            finally:
                ns[name]+=self.clock_ns()-started;calls[name]+=1
        began=self.clock_ns()
        try:
            p.buffer=_TimedBuffer(originals['buffer'],measure)
            for name in ('core','dma','gpio'):setattr(p,name,_TimedIO(originals[name],measure))
            p.sleep=lambda seconds:measure('wait_sleep',lambda:originals['sleep'](seconds))
            result=p.process(*args,**kwargs)
        finally:
            for name,value in originals.items():setattr(p,name,value)
            total=self.clock_ns()-began;ns['other']=total-sum(ns.values())
            self.last_timing=dict(total_ns=total,wall_ns=ns,calls=calls,
                valid=total>=0 and min(ns.values())>=0,
                scope='original finite-transfer wall time; scheduling/instrumentation included, not pure PL cycles')
            self.busy=False
        if not self.last_timing['valid']:raise RuntimeError('transport timing clock/partition invalid')
        return result


class LiveResources(VideoResources):
    def __init__(self,*args,clock_ns=time.monotonic_ns,**kwargs):
        super().__init__(*args,**kwargs)
        self.clock_ns=clock_ns;self.samples=[];self._post=None

    def open(self):
        identity=super().open()
        self.port=MeasuredPort(self.port,clock_ns=self.clock_ns)
        identity.update(reference_mode='two_frames_checked_only_after_hardware_cleanup',
            verification_ram_limit_bytes=1843200,image_history_saved=False)
        return identity

    def process_frame(self,*,sequence,timestamp_ns=None):
        began=self.clock_ns();self._available();self._stage('camera_read');camera_start=self.clock_ns()
        ok,bgr=self.camera.read()
        if not ok:raise RuntimeError('camera read failed; no retry')
        read_ns=time.monotonic_ns() if timestamp_ns is None else timestamp_ns
        validate_frame(bgr);self.captured+=1
        self._stage('finite_vision_transfer');vision_start=self.clock_ns()
        actual=self.port.process(bgr,sequence=sequence,timestamp_ns=read_ns)
        sample_start=self.clock_ns()
        if len(self.samples)<2:
            self.samples.append(dict(bgr=bgr.copy(),source_sequence=sequence,read_completed_ns=read_ns,vision=dict(actual)))
        hdmi_start=self.clock_ns();self._available();self._stage('hdmi_submit')
        self.last_frame=dict(source_sequence=sequence,read_completed_ns=read_ns,vision=actual,
            reference_checked=False,same_frame_equal=None,hdmi_submitted=False)
        shown=bgr.copy();cv=self.api.cv2
        cv.rectangle(shown,(160,120),(479,359),(0,255,0),1)
        cv.putText(shown,'LIVE PL | HEART OFF | seq='+str(sequence),(10,22),cv.FONT_HERSHEY_SIMPLEX,.48,(0,255,255),1)
        delta=str(actual['diff_sum']) if actual['difference_valid'] else 'N/A ('+actual['reason']+')'
        cv.putText(shown,'PL ROI luma='+str(actual['luma_sum'])+' diff='+delta,(10,44),cv.FONT_HERSHEY_SIMPLEX,.45,(0,255,255),1)
        self.pending=self.hdmi.newframe()
        if self.pending.shape!=(480,640,3) or self.pending.dtype!=np.dtype('uint8'):
            raise RuntimeError('HDMI frame is not packed BGR24')
        self.pending[:]=shown
        with self.guard.budget(1,'live frame submit'):
            while not int(self.guard.read(4))&0x1000:
                self._available();time.sleep(.001)
            self.hdmi.writeframe(self.pending)
        self.pending=None;self.submitted+=1;end=self.clock_ns()
        marks=(began,camera_start,vision_start,sample_start,hdmi_start,end)
        parts=dict(zip(('precheck','camera','vision','verification_capture','hdmi'),(b-a for a,b in zip(marks,marks[1:]))))
        if min(parts.values())<0:raise RuntimeError('live timing clock went backwards')
        self.last_frame.update(hdmi_submitted=True,timing=dict(total_ns=end-began,wall_ns=parts),
            transport_timing=self.port.last_timing)
        return dict(self.last_frame)

    def post_verify(self):
        if self._post is not None:return self._post
        if not self._cleanup or not self._cleanup.get('cleanup_complete') or self._cleanup.get('quarantine_required'):
            raise RuntimeError('post reference requires confirmed hardware cleanup')
        began=self.clock_ns();rows=[]
        try:
            for sample in self.samples:
                bgr=sample['bgr']
                expected=self.reference.process(bgr,sequence=sample['source_sequence'],timestamp_ns=sample['read_completed_ns'])
                reference={k:getattr(expected,k) for k in STAT_FIELDS}
                actual={k:sample['vision'][k] for k in STAT_FIELDS}
                mismatch={k:dict(reference=reference[k],pl=actual[k]) for k in STAT_FIELDS if reference[k]!=actual[k]}
                rows.append(dict(source_sequence=sample['source_sequence'],read_completed_ns=sample['read_completed_ns'],
                    bgr_sha256=hashlib.sha256(bgr.tobytes()).hexdigest(),expected=reference,actual=actual,
                    matched=not mismatch,mismatches=mismatch))
            self._post=dict(attempted=True,after_hardware_cleanup=True,sample_count=len(rows),total_frames=self.submitted,
                all_frames_verified=False,matched=len(rows)==2 and all(x['matched'] for x in rows),samples=rows,
                elapsed_ms=(self.clock_ns()-began)/1e6,images_saved=False)
            return self._post
        finally:self.samples.clear()
