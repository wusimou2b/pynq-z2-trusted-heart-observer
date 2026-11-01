"""Bounded HTML/SVG rendering and kernel-publish trace. No hardware calls."""
import html
import math
import time

SERIES = (('raw','原始去直流','#3578c4'),('mean','两点均值（25Hz）','#e28a24'),
          ('nlms_candidate','NLMS候选','#8a64b8'),('joint_output','联合保护输出（非纯NLMS）','#1c9275'))


def build_html(snapshot, value):
    history = snapshot.history[-500:]
    frames = [item.runtime.frame for item in history]
    times = [f.time_s for f in frames]
    points = [[getattr(f,key) for f in frames] for key,_,_ in SERIES]
    finite = [v for series in points for v in series if v is not None and math.isfinite(v)]
    xmin,xmax = (min(times),max(times)) if times else (0.,1.)
    ymin,ymax = (min(finite),max(finite)) if finite else (-1.,1.)
    dx,dy = max(xmax-xmin,.04),max(ymax-ymin,1e-9)
    paths = []
    for (key,label,color),values in zip(SERIES,points):
        commands, connected = [],False
        for x,y in zip(times,values):
            if y is None or not math.isfinite(y):
                connected = False
                continue
            commands.append('{}{:.2f},{:.2f}'.format('L' if connected else 'M',
                45+900*(x-xmin)/dx,235-210*(y-ymin)/dy))
            connected = True
        paths.append('<path data-series="{}" d="{}" fill="none" stroke="{}" stroke-width="1.5"/>'.format(
            key,' '.join(commands),color))
    text = ('状态：{state_cn}　序号：{sequence}　心率：{bpm_text}\n'
            '运动：{motion_cn}　质量：{quality_cn}　接触：{contact_cn}\n'
            '选路：{route_cn}　NLMS混合权重：{mix}\n{reason_cn}').format(**value)
    legend = '　'.join('<span style="color:{}">● {}</span>'.format(color,label) for _,label,color in SERIES)
    title = '历史曲线' if value['historical'] else '实时PPG（25Hz处理）'
    return ('<section style="font-family:sans-serif;max-width:1000px">'
        '<pre style="white-space:pre-wrap;font-size:15px">'+html.escape(text)+'</pre>'
        '<div>'+legend+'</div><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 280" '
        'role="img" aria-label="PPG历史波形" data-points="{}" data-first-sequence="{}">'.format(
            len(frames),frames[0].sequence if frames else '')+
        '<rect width="1000" height="280" fill="#fafbfc"/>'
        '<text x="45" y="17" font-size="13">'+title+' · 归一化PPG</text>'+
        ''.join(paths)+'<text x="45" y="260" font-size="12">{:.2f} 秒</text>'.format(xmin)+
        '<text x="900" y="260" font-size="12">{:.2f} 秒</text>'.format(xmax)+
        '</svg><p style="font-size:12px;color:#555">请核对序号持续更新；暂停/断连即历史，不能作为当前心率。'
        '原始50Hz / 处理25Hz；显示约2次/秒。非医疗用途。</p></section>')


def ipython_publisher(display_function=None):
    from IPython.display import HTML, display
    publish = display if display_function is None else display_function
    handle = None
    def send(markup):
        nonlocal handle
        value = HTML(markup)
        if handle is None:
            handle = publish(value,display_id=True)
            if handle is None or not hasattr(handle,'update'):
                raise RuntimeError('Notebook显示通道未返回更新句柄')
        else:
            handle.update(value)
    return send


class NotebookRenderer:
    def __init__(self,publish,*,clock=time):
        self.publish,self.clock = publish,clock
        self._attempts = []

    def __call__(self,snapshot,value):
        latest = snapshot.latest
        frame = latest.runtime.frame if latest is not None else None
        safety = snapshot.counts.get('raw_safety',{})
        trace = dict(at_ns=self.clock.monotonic_ns(),completed_ns=None,success=False,error='',
            sequence=frame.sequence if frame else None,
            read_completed_ns=latest.saved.record.read_completed_ns if latest else None,
            state=snapshot.state,faulted=snapshot.fault is not None,
            frame_allowed=frame.output_allowed if frame else False,frame_bpm=frame.bpm if frame else None,
            slot_generation=latest.slot.generation if latest else None,
            safety_generation=safety.get('generation'),contact_ready=safety.get('contact_ready',False),
            bpm_text=value['bpm_text'],historical=value['historical'])
        try:
            self.publish(build_html(snapshot,value))
            trace['success'] = True
        except BaseException as exc:
            trace['error'] = str(exc) or type(exc).__name__
            raise
        finally:
            trace['completed_ns'] = self.clock.monotonic_ns()
            self._attempts.append(trace)

    def metrics(self):
        return dict(attempts=[dict(item) for item in self._attempts])
