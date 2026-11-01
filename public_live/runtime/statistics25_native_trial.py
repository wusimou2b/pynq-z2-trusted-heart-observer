"""Native100 primitive proof, real-call coverage and unchanged whole-chain gate."""
import gc
import numpy as np

if __package__:
    from . import statistics25_replay as replay
    from .joint_startup import replace_attribute
    from .statistics25_native import METHODS, ACTIVE_METHODS, make_candidate
    from .ps_budget_runtime import no_hardware
else:
    import statistics25_replay as replay
    from joint_startup import replace_attribute
    from statistics25_native import METHODS, ACTIVE_METHODS, make_candidate
    from ps_budget_runtime import no_hardware


def primitive_proof(core):
    rng=np.random.default_rng(710)
    base=rng.normal(size=100)
    cases=[base,np.zeros(100),np.full(100,-0.),np.ones(100),base*1e-150,base*1e100,
           np.where(np.arange(100)==5,np.nan,base),np.where(np.arange(100)==5,np.inf,base)]
    fingerprints=[]
    def exact(actual,expected):
        if np.asarray(actual).tobytes()!=np.asarray(expected,dtype=float).tobytes():
            raise ValueError('native100 primitive bit mismatch')
    with np.errstate(all='ignore'):
        for x in cases:
            before=x.tobytes();left,right,nums=np.empty(30),np.empty(30),np.empty(30)
            core.quality_squares(x,left,right);products=left*right
            core.quality_numerators(x,products,nums)
            a,b,n=[],[],[]
            for lag in range(8,38):
                l,r=x[:-lag],x[lag:];p=(l@l)*(r@r)
                a.append(l@l);b.append(r@r);n.append(l@r if p>0 else 0.)
            exact(left,a);exact(right,b);exact(nums,n)
            if x.tobytes()!=before:raise ValueError('native100 input changed')
            parts=[np.ascontiguousarray(x[:100+lag] if lag<0 else x[lag:]) for lag in range(-5,6)]
            out=np.empty(11);core.norm_squares(parts,out)
            exact(out,[p.dot(p) for p in parts])
            den=np.array([0.,-0.,np.nan,np.inf,1.,2.,3.,4.,5.,6.,7.]);cross=np.empty(11)
            core.pair_numerators(parts,list(reversed(parts)),den,cross)
            exact(cross,[a@b if d!=0 else 0. for a,b,d in zip(parts,reversed(parts),den)])
            actual,squares=core.center_parts(x)
            for i,lag in enumerate(range(-5,6)):
                part=x[:100+lag] if lag<0 else x[lag:]
                centered=part-np.add.reduce(part,axis=None)/len(part)
                exact(actual[i],centered);exact(squares[i],centered.dot(centered))
            fingerprints.append(replay._fingerprint((left,right,nums,out,cross,actual,squares)))
    invalid=0
    for kind in ('shape','dtype','readonly','overlap'):
        x=base.copy();a=np.full(30,12.);b=np.full(30,34.)
        if kind=='shape':x=x[:-1]
        if kind=='dtype':x=x.astype(np.float32)
        if kind=='readonly':a.flags.writeable=False
        if kind=='overlap':b=a
        before=a.tobytes(),b.tobytes()
        try:core.quality_squares(x,a,b)
        except ValueError:invalid+=1
        else:raise ValueError('native100 accepted invalid buffer')
        if before!=(a.tobytes(),b.tobytes()):raise ValueError('native100 wrote rejected output')
    return dict(passed=True,cases=len(cases),invalid_cases=invalid,sha256=replay._fingerprint(fingerprints))


class _Coverage:
    def __init__(self,core):self.core=core;self.counts={name:0 for name in METHODS}
    def __getattr__(self,name):
        target=getattr(self.core,name)
        if name not in self.counts:return target
        def invoke(*args):
            self.counts[name]+=1
            return target(*args)
        return invoke


def run_trial(source,data,core,*,host_check=False,emit=print):
    report=dict(primitive=None,proof=None,timing=None,error=None,diagnostic_complete=False,
                candidate_budget_passed=False,native_validation_calls={},
                implementation=core.implementation,hardware_accessed=False,original_ipc_started=False,
                original_ps_exit_fixed=False)
    before=gc.isenabled(),list(gc.get_threshold());err_before=np.geterr()
    stage='primitive'
    try:
        with no_hardware():
            report['primitive']=primitive_proof(core)
            counted=_Coverage(core)
            stage='strict_proof'
            with replace_attribute(replay,'make_candidate',lambda:make_candidate(counted)):
                report['proof']=replay.qualify(source,data,host_check=host_check,emit=emit)
            report['native_validation_calls']=dict(counted.counts)
            if not report['proof']['passed'] or not all(counted.counts[name] for name in ACTIVE_METHODS):
                raise ValueError('strict proof or actual native coverage failed')
            stage='ordinary_timing'
            # No coverage wrappers in the ordinary timing phase.
            with replace_attribute(replay,'make_candidate',lambda:make_candidate(core)):
                report['timing']=replay.measure(source,data,report['proof'],host_check=host_check,emit=emit)
            report['diagnostic_complete']=True
            report['candidate_budget_passed']=report['timing']['gate']['passed']
    except BaseException as exc:
        report['error']=dict(stage=stage,type=type(exc).__name__,message=str(exc))
    report.update(gc_before=before,gc_after=(gc.isenabled(),list(gc.get_threshold())),
                  numpy_error_mode_before=err_before,numpy_error_mode_after=np.geterr())
    report['configuration_unchanged']=(report['gc_before']==report['gc_after'] and
                                     report['numpy_error_mode_before']==report['numpy_error_mode_after'])
    if not report['configuration_unchanged']:
        report['error']=report['error'] or dict(stage='configuration',type='RuntimeError',message='GC/NumPy config changed')
    if report['error']:report['diagnostic_complete']=report['candidate_budget_passed']=False
    return report
