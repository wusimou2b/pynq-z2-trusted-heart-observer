"""Private100-point statistics classes backed by the newly built dtype-dot core."""
import hashlib
import importlib.util
from pathlib import Path
from types import BuiltinFunctionType

METHODS=('quality_squares','quality_numerators','norm_squares','pair_numerators','center_parts')
ACTIVE_METHODS=('quality_squares','quality_numerators','pair_numerators','center_parts')


def load_native(binary):
    path=Path(binary['path']).resolve(strict=True)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=binary['sha256']:
        raise ValueError('native100 binary identity changed')
    spec=importlib.util.spec_from_file_location('_v3b25_statistics_dot',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if (module.implementation!='numpy_dtype_dotfunc_100_v2' or
            any(not isinstance(getattr(module,name),BuiltinFunctionType) for name in METHODS) or
            Path(module.__file__).resolve()!=path):
        raise ValueError('native100 loaded implementation differs')
    return module


def make_candidate(core):
    import numpy as np
    from types import SimpleNamespace
    from entry25_candidate import DelayedPeakChain, DelayedSelector25
    from heart_v2.metrics import _matching_vectors
    from heart_v3a.live.numpy_compat import _bind
    from v3a_rate25 import benefit,state
    from v3a_rate25.policy import HISTORY,PERIOD_LAGS,CORRELATION_LAG
    if (HISTORY!=100 or list(PERIOD_LAGS)!=list(range(8,38)) or CORRELATION_LAG!=5 or
            core.implementation!='numpy_dtype_dotfunc_100_v2'):
        raise ValueError('native100 algorithm/core identity differs')

    class QualityCache(state.QualityCache25):
        def get(self,values):
            if values.dtype!=np.dtype(float):return super().get(values)
            if values.shape!=(100,) or not np.isfinite(values).all():
                raise ValueError('25Hz质量统计需要100个有限数')
            key=values.tobytes()
            if key not in self.entries:
                centered=values-values.mean()
                left,right=np.empty(30),np.empty(30)
                core.quality_squares(centered,left,right)
                products=left*right;nums=np.empty(30)
                core.quality_numerators(centered,products,nums)
                norms=np.sqrt(products);scores=np.zeros(30)
                np.divide(nums,norms,out=scores,where=norms>0)
                periodicity=max(0.,*(float(v) for v in scores))
                high,low=np.percentile(values,[95,5])
                self.entries[key]=float(high-low),min(1.,periodicity)
                if len(self.entries)>4:self.entries.popitem(last=False)
            self.entries.move_to_end(key)
            return self.entries[key]

    class WindowMetrics(benefit.WindowMetrics25):
        def _parts(self,values,key,maximum):
            cache_key=key,maximum
            if cache_key not in self.parts:
                if maximum!=5:raise ValueError('native100 history lag must be5')
                parts,squares=core.center_parts(values)
                self.parts[cache_key]=parts,np.sqrt(squares)
            return self.parts[cache_key]

        def correlation(self,output,reference_signal):
            output,reference_signal=_matching_vectors(output,reference_signal)
            if not (np.isfinite(output).all() and np.isfinite(reference_signal).all()):
                raise ValueError('correlation inputs must contain only finite values')
            if output.shape!=(100,):raise ValueError('native100 correlation requires100 points')
            ykey,xkey=self._key(output),self._key(reference_signal)
            key=ykey,xkey,5
            if key not in self.correlations:
                ys,yn=self._parts(output,ykey,5);xs,xn=self._parts(reference_signal,xkey,5)
                denominators=yn*xn[::-1];nums=np.empty(11)
                core.pair_numerators(ys,list(reversed(xs)),denominators,nums)
                scores=np.zeros(11)
                np.divide(nums,denominators,out=scores,where=denominators!=0)
                self.correlations[key]=max((abs(float(v)) for v in scores),default=0.)
            return self.correlations[key]

    assess=_bind(benefit.assess_history25,WindowMetrics25=WindowMetrics)
    class Selector(DelayedSelector25):
        step=_bind(DelayedSelector25.step,assess_history25=assess)
    class Chain(DelayedPeakChain):
        def _reset_signals(self):
            super()._reset_signals();cache=QualityCache()
            for component in self.quality_components.values():component.window_cache=cache
            self.selector=Selector()
    return SimpleNamespace(Chain=Chain,QualityCache=QualityCache,WindowMetrics=WindowMetrics,
                           Selector=Selector,assess_history=assess)
