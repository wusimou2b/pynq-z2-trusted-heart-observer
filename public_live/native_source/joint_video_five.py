"""One camera/video thread; drain grabs, admit 5fps under the heart's epoch."""
import json
from pathlib import Path
import threading
import time

if __package__:
    from .joint_video_live_guard import FLAGS,MODE
    from .joint_video_runtime import describe
else:
    from joint_video_live_guard import FLAGS,MODE
    from joint_video_runtime import describe

PERIOD_NS=200_000_000
DURATION_NS=60_000_000_000


class VideoFive:
    def __init__(self,resources,output,*,clock_ns=time.monotonic_ns):
        self.resources,self.output,self.clock_ns=resources,Path(output),clock_ns
        self._stop=threading.Event();self._ready=threading.Event();self._arm_lock=threading.Lock()
        self._thread=None;self._active=False;self._attempted=False
        self.started_ns=self.ended_ns=self.first_admitted_ns=self.last_admitted_ns=None
        self.first_submitted_ns=self.last_submitted_ns=None
        self.fault=None;self.stop_reason=None
        self.metrics=dict(completed_frames=0,records_saved=0,valid_difference_frames=0,missed_target_slots=0,
            formal_elapsed_seconds=0.,application_submit_fps=0.,max_frame_processing_ms=0.,
            grabs_total=0,preparation_grabs=0,formal_grabs=0,selected_grabs=0,unselected_formal_grabs=0,
            terminal_grabs=0,terminal_retrieves=0,formal_submitted_frames=0,tail_completed_frames=0)

    def arm(self,started_ns):
        if type(started_ns) is not int or started_ns<=0:raise ValueError('heart epoch must be positive integer ns')
        with self._arm_lock:
            if self.started_ns is not None or self._stop.is_set():raise RuntimeError('video epoch already armed or stopped')
            self.started_ns=started_ns

    def request_stop(self):self._stop.set()
    def is_alive(self):return self._active or bool(self._thread and self._thread.is_alive())

    def start(self):
        if self._thread is not None or self._attempted:raise RuntimeError('video thread already attempted')
        self._thread=threading.Thread(target=self.run,name='joint-five-fps-video',daemon=False)
        self._thread.start()
        if not self._ready.wait(3.):
            self.request_stop();raise TimeoutError('video thread startup not ready')
        if self.fault:raise RuntimeError('video thread failed: '+self.fault['message'])

    def join(self,timeout):
        if self._thread is not None:self._thread.join(timeout)
        return not self.is_alive()

    def run(self):
        if self._attempted:raise RuntimeError('video loop already attempted')
        self._attempted=True;self._active=True;m=self.metrics;slot=0
        try:
            with (self.output/'frames.jsonl').open('x',encoding='utf-8') as sink:
                self._ready.set()
                while not self._stop.is_set():
                    if not self.resources.camera.grab():raise RuntimeError('camera grab failed; no retry')
                    grabbed_ns=self.clock_ns();grab_sequence=m['grabs_total'];m['grabs_total']+=1
                    epoch=self.started_ns
                    if epoch is None or grabbed_ns<epoch:
                        m['preparation_grabs']+=1;continue
                    deadline=epoch+DURATION_NS
                    if grabbed_ns>=deadline:
                        m['terminal_grabs']+=1;break
                    m['formal_grabs']+=1;due=epoch+slot*PERIOD_NS
                    if grabbed_ns<due or self._stop.is_set():
                        m['unselected_formal_grabs']+=1;continue
                    missed=max(0,(grabbed_ns-due)//PERIOD_NS)
                    slot+=missed;m['missed_target_slots']+=missed
                    ok,bgr=self.resources.camera.retrieve();read_ns=self.clock_ns()
                    if not ok:raise RuntimeError('camera retrieve failed; no retry')
                    if read_ns>=deadline or self._stop.is_set():
                        m['terminal_retrieves']+=1;break
                    m['selected_grabs']+=1
                    if self.first_admitted_ns is None:self.first_admitted_ns=read_ns
                    self.last_admitted_ns=read_ns
                    began=self.clock_ns()
                    row=self.resources.process_ready_frame(bgr,sequence=m['completed_frames'],timestamp_ns=read_ns)
                    submitted_ns=self.clock_ns()
                    row.update(camera_grab_sequence=grab_sequence,grab_completed_ns=grabbed_ns,
                        admitted_ns=read_ns,submitted_ns=submitted_ns,target_slot=slot,
                        completed_after_formal_end=submitted_ns>deadline)
                    sink.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');sink.flush()
                    m['completed_frames']+=1;m['records_saved']+=1
                    m['valid_difference_frames']+=int(row['vision']['difference_valid'])
                    m['formal_submitted_frames']+=int(submitted_ns<=deadline)
                    m['tail_completed_frames']+=int(submitted_ns>deadline)
                    m['max_frame_processing_ms']=max(m['max_frame_processing_ms'],(submitted_ns-began)/1e6)
                    if self.first_submitted_ns is None:self.first_submitted_ns=submitted_ns
                    self.last_submitted_ns=submitted_ns;slot+=1
        except BaseException as exc:
            self.fault=describe(exc,'video_thread');self.stop_reason='fault'
        finally:
            self.ended_ns=self.clock_ns()
            if self.started_ns is not None:
                m['formal_elapsed_seconds']=max(0,min(self.ended_ns-self.started_ns,DURATION_NS))/1e9
                if m['formal_elapsed_seconds']:
                    m['application_submit_fps']=m['formal_submitted_frames']/m['formal_elapsed_seconds']
            if self.stop_reason is None:
                self.stop_reason=('duration_complete' if self.started_ns is not None and
                    self.ended_ns>=self.started_ns+DURATION_NS else 'stop_requested')
            self._active=False;self._ready.set()

    def report(self):
        return dict(schema='v3b25_concurrent_video_v1',**FLAGS,requested_formal_seconds=60,target_application_fps=5,
            reference_mode=MODE,formal_reference_calls=0,all_frames_reference_verified=False,
            target_15fps_observed=self.metrics['application_submit_fps']>=15,
            target_5fps_observed=self.metrics['application_submit_fps']>=5,
            formal_started_ns=self.started_ns,formal_deadline_ns=self.started_ns+DURATION_NS if self.started_ns else None,
            video_loop_ended_ns=self.ended_ns,first_admitted_ns=self.first_admitted_ns,last_admitted_ns=self.last_admitted_ns,
            first_submitted_ns=self.first_submitted_ns,last_submitted_ns=self.last_submitted_ns,
            grabs_are_exposure_counter=False,source_sequence_scope='accepted frames; camera_grab_sequence is successful software grabs, not sensor exposures',
            timing_scope=dict(frame_parts='after retrieve; camera part is the ready-frame adapter, not USB camera latency',
                retrieve='admitted_ns minus grab_completed_ns; includes scheduling',
                exposure_to_screen_measured=False),
            thread_exited=not self.is_alive(),stop_reason=self.stop_reason,fault=self.fault,metrics=dict(self.metrics))
