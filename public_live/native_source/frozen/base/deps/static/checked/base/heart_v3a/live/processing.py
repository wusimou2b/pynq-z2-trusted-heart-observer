"""实时固定SOS、系数复用及旧NumPy积分兼容；因果状态完整清零。"""
from collections import deque

from heart_v2.preprocess import CausalDcBlocker
from .statistics_fast import (LeanJointBenefitSelector as JointBenefitSelector, runtime_step,
    CachedBranchQuality as BranchQuality, QualityWindowCache,
    CachedSosHeartRateDetector as CausalHeartRateDetector)
from heart_v2.runtime_state import MotionClassifier
from heart_v3a.runtime_pl_chain import RuntimePlMainChain


class ReusingRuntimePlMainChain(RuntimePlMainChain):
    """处理公式沿用只读原主链；不在每次重置时重新设计带通系数。"""

    step = runtime_step

    def _reset_signals(self):
        prep = self.config["preprocess"]
        self.ppg_dc = CausalDcBlocker(prep["ppg_dc_alpha"])
        self.ref_dc = [CausalDcBlocker(prep["reference_dc_alpha"]) for _ in range(4)]
        self.mean_window = deque(maxlen=4)
        self.selector = JointBenefitSelector()
        self.motion_classifier = MotionClassifier()
        parameters = self.config["heartrate"]
        configuration = tuple(sorted(parameters.items()))
        if getattr(self, "_heartrate_configuration", None) != configuration:
            self.detectors = {key: CausalHeartRateDetector(50., **parameters)
                              for key in ("raw", "mean", "nlms", "joint")}
            self.output_detector = CausalHeartRateDetector(50., **parameters)
            self._heartrate_configuration = configuration
        else:
            # 只保留固定系数；zi、阈值、峰位置及全部 IBI 历史必须重新初始化。
            for detector in self.detectors.values():
                detector.reset()
            self.output_detector.reset()
        window_cache = QualityWindowCache()
        self.quality_components = {key: BranchQuality(window_cache) for key in self.detectors}
        self.previous_route = "none"
