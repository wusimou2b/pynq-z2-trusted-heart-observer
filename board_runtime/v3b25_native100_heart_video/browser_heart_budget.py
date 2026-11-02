"""Ordinary display-data preparation budget; no board I/O, kernel or browser."""
import json
import math
import multiprocessing as mp
from pathlib import Path
from statistics import median
import sys
import time
from types import SimpleNamespace as N


def sample(i):
    frame=N(sequence=i,time_s=i/25,raw=math.sin(i*.29),mean=math.sin(i*.29-.1),
        nlms_candidate=math.cos(i*.27),joint_output=math.sin(i*.29-.05),output_allowed=True,bpm=70.,
        motion='static',selected_quality='good',contact_ready=True,selected_route='mean',nlms_mix=0.,
        reason_cn='仅合成显示预算，不是真实心率')
    item=N(runtime=N(frame=frame),slot=N(generation=0),saved=N(record=N(read_completed_ns=10_000_000_000)))
    return N(state='running',fault=None,latest=item,history=(item,),
        counts={'raw_safety':{'generation':0,'contact_ready':True}})


class Clock:
    @staticmethod
    def monotonic_ns():return 10_020_000_000


class JsonComm:
    def __init__(self):self.bytes=0
    def send(self,value):self.bytes+=len(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode())


def run_budget(root,checked):
    root=Path(root);output=root/'browser-budget.json'
    if output.exists():return validate_budget(output,checked['package_manifest_sha256'])
    class NoHardware:
        def find_spec(self,fullname,path=None,target=None):
            if fullname.split('.')[0] in ('pynq','smbus','smbus2','spidev'):
                raise RuntimeError('hardware import prohibited in display budget')
    block=NoHardware();sys.meta_path.insert(0,block)
    if __package__:
        from .run_startup180 import load_display
        from . import browser_heart_transport as reader
        from .browser_heart_display import BrowserRenderer,BrowserBridge
    else:
        from run_startup180 import load_display
        import browser_heart_transport as reader
        from browser_heart_display import BrowserRenderer,BrowserBridge
    display=load_display(root)
    context,cached=display.bootstrap(root/'frozen/base',algorithm=False)
    candidate=display.load_owner(root/'frozen/base').prepare_display(context)
    from owner25 import transport
    from v3a_25hz_live.view import presentation25
    ctx=mp.get_context('spawn');clock=Clock();fixture=[sample(i) for i in range(700)]
    old_base,old_protocol=reader._BASE_MAILBOX,reader._TRANSPORT
    reader._BASE_MAILBOX,reader._TRANSPORT=transport.Mailbox,transport
    rounds=[];initials=[];functional=True
    try:
        a,b=transport.Mailbox(ctx),reader.BrowserMailbox(ctx)
        for s in fixture[:500]:a.publish(s,now_ns=10_020_000_000);b.publish(s,now_ns=10_020_000_000)
        original=a.snapshot(now_ns=clock.monotonic_ns())
        delta=b.curve_delta(b.snapshot(now_ns=clock.monotonic_ns()),None)
        wanted=[[getattr(item.runtime.frame,k) for k in transport.FIELDS] for item in original.history]
        functional=delta['rows']==wanted
        for group in range(4):
            for mode in ('A','B','B','A'):
                box=transport.Mailbox(ctx) if mode=='A' else reader.BrowserMailbox(ctx)
                for s in fixture[:500]:box.publish(s,now_ns=10_020_000_000)
                sink=JsonComm()
                if mode=='A':
                    renderer=cached.CachedRenderer(lambda markup:sink.send({'data':{'text/html':markup}}),
                        candidate.CachedSvgBuilder(),clock=clock)
                else:
                    bridge=BrowserBridge(clock=clock);bridge.comm=sink;bridge.ready=True
                    renderer=BrowserRenderer(bridge,clock=clock)
                view=box.snapshot(now_ns=clock.monotonic_ns())
                t=time.perf_counter_ns();renderer(view,presentation25(view,clock.monotonic_ns()))
                initials.append(dict(mode=mode,wall_ns=time.perf_counter_ns()-t))
                elapsed=cpu=0;cursor=500
                for index in range(12):
                    count=12+index%2
                    for s in fixture[cursor:cursor+count]:box.publish(s,now_ns=10_020_000_000)
                    cursor+=count
                    wall=time.perf_counter_ns();used=time.process_time_ns()
                    for _ in range(50):
                        box.touch();view=box.snapshot(now_ns=clock.monotonic_ns())
                        value=presentation25(view,clock.monotonic_ns())
                    renderer(view,value)
                    box.touch();fresh=box.snapshot(now_ns=clock.monotonic_ns())
                    presentation25(fresh,clock.monotonic_ns())
                    cpu+=time.process_time_ns()-used;elapsed+=time.perf_counter_ns()-wall
                rounds.append(dict(group=group,mode=mode,cycles=12,status_polls_per_cycle=51,
                    wall_ns=elapsed,cpu_ns=cpu,json_payload_bytes=sink.bytes))
        aa=[r['wall_ns'] for r in rounds if r['mode']=='A'];bb=[r['wall_ns'] for r in rounds if r['mode']=='B']
        group_better=all(median(r['wall_ns'] for r in rounds if r['group']==g and r['mode']=='B') <
                         median(r['wall_ns'] for r in rounds if r['group']==g and r['mode']=='A') for g in range(4))
        result=dict(schema='v3b25_browser_budget_v1',package_manifest_sha256=checked['package_manifest_sha256'],
            curve_values_identical=functional,ordinary_rounds=len(rounds),rounds=rounds,initial_sync=initials,
            median_original_wall_ns=median(aa),median_browser_wall_ns=median(bb),
            wall_reduction_fraction=1-median(bb)/median(aa),each_group_lower=group_better,
            passed=functional and group_better and median(bb)<=.8*median(aa),hardware_accessed=False,
            platform=sys.platform,python=sys.version,
            scope='synthetic500-point display: metadata polls/presentation + real SVG or delta + JSON-send preparation; no actual ZMQ/USB/browser/hardware',
            arm_result=bool(sys.platform=='linux' and __import__('platform').machine() in ('armv7l','aarch64')),
            real_comm_measured=False,live_25hz_passed=False)
        with output.open('x',encoding='utf-8') as stream:json.dump(result,stream,ensure_ascii=False,indent=2)
    finally:
        reader._BASE_MAILBOX,reader._TRANSPORT=old_base,old_protocol
        sys.meta_path.remove(block)
    if not result['passed']:raise RuntimeError('display preparation budget lacks stable20% benefit; do not start capture')
    return result


def validate_budget(path,manifest):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    rounds=data.get('rounds',[])
    if (data.get('schema')!='v3b25_browser_budget_v1' or data.get('package_manifest_sha256')!=manifest
            or data.get('passed') is not True or data.get('curve_values_identical') is not True or len(rounds)!=16):
        raise ValueError('missing or failed display-data budget; run the first cell')
    for g in range(4):
        a=[r['wall_ns'] for r in rounds if r.get('group')==g and r.get('mode')=='A']
        b=[r['wall_ns'] for r in rounds if r.get('group')==g and r.get('mode')=='B']
        if len(a)!=2 or len(b)!=2 or any(type(v) is not int or v<=0 for v in a+b) or median(b)>=median(a):
            raise ValueError('display budget group invalid')
    a=[r['wall_ns'] for r in rounds if r['mode']=='A'];b=[r['wall_ns'] for r in rounds if r['mode']=='B']
    if median(b)>.8*median(a):raise ValueError('display budget benefit insufficient')
    return data
