"""Private 25Hz statistics: batch independent ufuncs, keep each dot reduction."""


def make_candidate():
    import numpy as np
    from types import SimpleNamespace
    from entry25_candidate import DelayedPeakChain, DelayedSelector25
    from heart_v2.metrics import _matching_vectors, _validate_max_lag
    from heart_v3a.live.numpy_compat import _bind
    from v3a_rate25 import benefit, state
    from v3a_rate25.policy import HISTORY, PERIOD_LAGS, CORRELATION_LAG

    class QualityCache(state.QualityCache25):
        def get(self, values):
            if values.shape != (HISTORY,) or not np.isfinite(values).all():
                raise ValueError('25Hz质量统计需要100个有限数')
            key = values.tobytes()
            if key not in self.entries:
                centered = values - values.mean()
                products = np.empty(len(PERIOD_LAGS), dtype=centered.dtype)
                numerators = np.zeros_like(products)
                for index, lag in enumerate(PERIOD_LAGS):
                    left, right = centered[:-lag], centered[lag:]
                    product = (left @ left) * (right @ right)
                    products[index] = product
                    if product > 0:
                        numerators[index] = left @ right
                norms = np.sqrt(products)
                scores = np.zeros_like(products)
                np.divide(numerators, norms, out=scores, where=norms > 0)
                periodicity = max(0., *(float(score) for score in scores))
                # NumPy scalar-q float32 promotion differs from array-q. The
                # actual chain supplies float64; keep other dtypes' old calls.
                if values.dtype == np.dtype(float):
                    high, low = np.percentile(values, [95, 5])
                else:
                    high, low = np.percentile(values, 95), np.percentile(values, 5)
                self.entries[key] = float(high - low), min(1., periodicity)
                if len(self.entries) > 4:
                    self.entries.popitem(last=False)
            self.entries.move_to_end(key)
            return self.entries[key]

    class WindowMetrics(benefit.WindowMetrics25):
        def _parts(self, values, key, maximum):
            cache_key = key, maximum
            if cache_key not in self.parts:
                n, parts, squares = len(values), [], []
                limit = min(maximum, n - 2)
                for lag in range(-limit, limit + 1):
                    part = values[:n + lag] if lag < 0 else values[lag:]
                    centered = part - np.add.reduce(part, axis=None) / len(part)
                    parts.append(centered)
                    squares.append(centered.dot(centered))
                norms = np.sqrt(np.asarray(squares))
                self.parts[cache_key] = list(zip(parts, norms))
            return self.parts[cache_key]

        def correlation(self, output, reference_signal):
            maximum = _validate_max_lag(CORRELATION_LAG)
            output, reference_signal = _matching_vectors(output, reference_signal)
            if not (np.isfinite(output).all() and np.isfinite(reference_signal).all()):
                raise ValueError('correlation inputs must contain only finite values')
            output_key, reference_key = self._key(output), self._key(reference_signal)
            key = output_key, reference_key, maximum
            if key not in self.correlations:
                ys = self._parts(output, output_key, maximum)
                xs = self._parts(reference_signal, reference_key, maximum)
                numerators = np.empty(len(ys), dtype=float)
                denominators = np.empty_like(numerators)
                for index, ((y, yn), (x, xn)) in enumerate(zip(ys, reversed(xs))):
                    denominator = yn * xn
                    denominators[index] = denominator
                    numerators[index] = y @ x if denominator != 0 else 0.
                scores = np.zeros_like(numerators)
                np.divide(numerators, denominators, out=scores, where=denominators != 0)
                self.correlations[key] = max((abs(float(v)) for v in scores), default=0.)
            return self.correlations[key]

    assess = _bind(benefit.assess_history25, WindowMetrics25=WindowMetrics)

    class Selector(DelayedSelector25):
        step = _bind(DelayedSelector25.step, assess_history25=assess)

    class Chain(DelayedPeakChain):
        def _reset_signals(self):
            super()._reset_signals()
            cache = QualityCache()
            for component in self.quality_components.values():
                component.window_cache = cache
            self.selector = Selector()

    return SimpleNamespace(Chain=Chain, QualityCache=QualityCache, WindowMetrics=WindowMetrics,
                           assess_history=assess, Selector=Selector)
