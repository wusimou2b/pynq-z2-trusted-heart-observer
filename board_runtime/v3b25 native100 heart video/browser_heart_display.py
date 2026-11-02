"""Bounded comm packets for browser Canvas; no SVG or history object rebuild."""
from contextlib import ExitStack, contextmanager
import importlib
import json
import math
from pathlib import Path
import time
import uuid

_ACTIVE = None


class BrowserBridge:
    def __init__(self, *, clock=time):
        self.clock=clock; self.comm=None; self.ready=False; self.closed=False
        self.server_ms=None; self.client_sent_ms=None; self.handshake_rtt_ms=None
        self.packet_count=0; self.payload_bytes=0

    def opened(self, comm, message):
        data=message.get('content',{}).get('data',{})
        sent=data.get('client_sent_ms')
        if self.comm is not None or data.get('kind')!='sync' or type(sent) not in (float,int) or not math.isfinite(sent):
            raise ValueError('invalid browser clock handshake')
        self.comm=comm; self.client_sent_ms=sent
        self.server_ms=self.clock.monotonic_ns()/1e6
        comm.on_msg(self.message); comm.on_close(self.disconnected)
        comm.send(dict(kind='sync',client_sent_ms=sent,server_ms=self.server_ms))

    def message(self, message):
        data=message.get('content',{}).get('data',{})
        sent,received=data.get('client_sent_ms'),data.get('client_received_ms')
        if (self.closed or data.get('kind')!='ready' or data.get('server_ms')!=self.server_ms
                or sent!=self.client_sent_ms or type(received) not in (float,int)
                or not math.isfinite(received) or not 0<=received-sent<=250):
            self.ready=False
            return
        self.handshake_rtt_ms=received-sent; self.ready=True

    def disconnected(self, message):
        self.closed=True; self.ready=False

    def require_ready(self):
        if not self.ready or self.closed or self.comm is None:
            raise RuntimeError('browser display not ready; wait for the green message after the first cell')
        return self

    def send(self, packet):
        self.require_ready()
        # Reject nonfinite data before handing it to IPython's serializer.
        encoded=json.dumps(packet,ensure_ascii=False,allow_nan=False,separators=(',',':'))
        self.comm.send(packet)
        self.packet_count+=1; self.payload_bytes+=len(encoded.encode('utf-8'))

    def close(self):
        self.closed=True; self.ready=False
        if self.comm is not None:self.comm.close()

    def report(self):
        return dict(ready=self.ready,closed=self.closed,handshake_rtt_ms=self.handshake_rtt_ms,
                    packet_count=self.packet_count,payload_bytes=self.payload_bytes,
                    browser_render_measured=False)


def prepare_browser():
    """First cell returns so the kernel can process the browser's clock handshake."""
    global _ACTIVE
    from IPython import get_ipython
    from IPython.display import HTML,Javascript,display
    shell=get_ipython(); kernel=getattr(shell,'kernel',None)
    if kernel is None:raise RuntimeError('需要经典Jupyter Notebook')
    if _ACTIVE is not None and not _ACTIVE.closed:
        raise RuntimeError('browser display already prepared; keep this first-cell result')
    bridge=BrowserBridge(); token='heart25-'+uuid.uuid4().hex
    kernel.comm_manager.register_target(token,bridge.opened)
    markup=('<div id="'+token+'" style="max-width:1000px;font:14px sans-serif">'
        '<p data-ready>正在连接浏览器绘图，请等待绿色就绪提示</p><pre data-status>心率：N/A</pre>'
        '<p data-note>等待数据</p><p style="font-size:12px">'
        '<span style="color:#4b83d1">● 原始去直流</span>　'
        '<span style="color:#df9b22">● 两点均值</span>　'
        '<span style="color:#5aaf79">● NLMS候选</span>　'
        '<span style="color:#cf5774">● 联合保护输出</span></p>'
        '<canvas width="960" height="280" style="width:100%;border:1px solid #dde2e8"></canvas>'
        '<p style="font-size:12px">有效原始25Hz／处理25Hz；四曲线在电脑浏览器绘制。暂停/断连即历史，非医疗用途。</p></div>')
    source=Path(__file__).with_name('browser_heart_client.js').read_text(encoding='utf-8')
    display(HTML(markup)); display(Javascript(source+'\nHeartWave.boot('+json.dumps(dict(id=token,target=token))+');'))
    _ACTIVE=bridge
    return bridge


def ready_bridge():
    if _ACTIVE is None:raise RuntimeError('browser display not ready; run the first cell first')
    return _ACTIVE.require_ready()


class BrowserRenderer:
    def __init__(self, publish, builder=None, *, clock=time):
        self.publish=publish.send if hasattr(publish,'send') else publish
        self.clock=clock; self.cursor=None; self.index=0; self._attempts=[]; self._reader={}

    def __call__(self, snapshot, value):
        latest=snapshot.latest; frame=latest.runtime.frame if latest else None
        safety=snapshot.counts.get('raw_safety',{})
        start=self.clock.monotonic_ns()
        trace=dict(at_ns=start,completed_ns=None,success=False,error='',
            sequence=frame.sequence if frame else None,
            read_completed_ns=latest.saved.record.read_completed_ns if latest else None,
            state=snapshot.state,faulted=snapshot.fault is not None,
            frame_allowed=frame.output_allowed if frame else False,frame_bpm=frame.bpm if frame else None,
            slot_generation=latest.slot.generation if latest else None,
            safety_generation=safety.get('generation'),contact_ready=safety.get('contact_ready',False),
            bpm_text=value['bpm_text'],historical=value['historical'],build_ns=None,publish_ns=None)
        split=None
        try:
            delta=snapshot.curve_source.curve_delta(snapshot,self.cursor)
            now=self.clock.monotonic_ns()
            eligible=bool(value['bpm_text']!='N/A' and not value['historical']
                and trace['state']=='running' and not trace['faulted'] and trace['frame_allowed']
                and trace['contact_ready'] and trace['slot_generation']==trace['safety_generation'])
            packet=dict(kind='frame',index=self.index,issued_ms=now/1e6,
                read_ms=trace['read_completed_ns']/1e6 if latest else None,
                eligible=eligible,bpm_text=value['bpm_text'],historical=value['historical'],
                state=snapshot.state,generation=trace['safety_generation'],status=dict(value),curves=delta)
            split=self.clock.monotonic_ns();trace['build_ns']=split-start
            self.publish(packet)
            self.cursor=delta['last'];self.index+=1;trace['success']=True
            self._reader=snapshot.curve_source.reader_stats()
        except BaseException as exc:
            trace['error']=str(exc) or type(exc).__name__
            raise
        finally:
            end=self.clock.monotonic_ns();trace['completed_ns']=end
            if split is None:trace['build_ns']=end-start
            else:trace['publish_ns']=end-split
            self._attempts.append(trace)

    def metrics(self):
        return dict(attempts=[dict(a) for a in self._attempts],renderer='browser_canvas_v1',
                    cache=dict(self._reader),browser_render_measured=False)


@contextmanager
def install_browser_display(root, bridge):
    """Keep the original parent lifecycle and permission checks unchanged."""
    if __package__:
        from .run_startup180 import load_display
        from .joint_startup import replace_attribute
        from . import browser_heart_transport as reader
    else:
        from run_startup180 import load_display
        from joint_startup import replace_attribute
        import browser_heart_transport as reader
    bridge.require_ready(); display=load_display(root); original=display.bootstrap
    installed=False
    with ExitStack() as stack:
        def bootstrap(*args,**kwargs):
            nonlocal installed
            result=original(*args,**kwargs)
            if not installed:
                protocol=importlib.import_module('owner25.transport')
                render=importlib.import_module('display25.render')
                stack.enter_context(replace_attribute(reader,'_BASE_MAILBOX',protocol.Mailbox))
                stack.enter_context(replace_attribute(reader,'_TRANSPORT',protocol))
                stack.enter_context(replace_attribute(protocol,'Mailbox',reader.BrowserMailbox))
                stack.enter_context(replace_attribute(result[1],'CachedRenderer',BrowserRenderer))
                stack.enter_context(replace_attribute(render,'ipython_publisher',lambda:bridge))
                installed=True
            return result
        stack.enter_context(replace_attribute(display,'bootstrap',bootstrap))
        yield
