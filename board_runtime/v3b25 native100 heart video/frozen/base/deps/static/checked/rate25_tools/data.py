"""Bound raw observations, fixed integer vectors, and software reference."""
from dataclasses import asdict
import json
from pathlib import Path

from heart_v2.runtime_main_chain import Observation
from heart_v3a.runtime_backend import FixedNlmsBackend
from v3a_rate25.frontend import RawFrontend
from peak_chain import PeakTimingChain


def load_cases(root):
    root = Path(root)
    inputs = json.loads((root/'inputs/cases.json').read_text(encoding='utf8'))
    vectors = json.loads((root/'inputs/vectors.json').read_text(encoding='utf8'))
    cases = []
    if len(inputs) != 2 or len(vectors) != 2: raise ValueError('必须完整两组输入')
    for source, target in zip(inputs, vectors):
        if source['name'] != target['name']: raise ValueError('向量案例错序')
        observations = [Observation(**{**row, 'axes_g': tuple(row['axes_g'])}) for row in source['raw']]
        if len(target['vectors']) != len(observations)//2: raise ValueError('向量计数不符')
        cases.append(dict(name=source['name'], observations=observations, vectors=target['vectors']))
    return cases


def canonical(value):
    """JSON-normalized dataclass: tuple references intentionally become arrays."""
    return json.loads(json.dumps(asdict(value), allow_nan=False))


class RecordingBackend(FixedNlmsBackend):
    def __init__(self):
        super().__init__()
        self.vectors = []

    def transact(self, packet):
        reply = super().transact(packet)
        self.vectors.append(dict(packet=canonical(packet), reply=canonical(reply)))
        return reply


def reference(observations):
    backend, front = RecordingBackend(), RawFrontend()
    chain = PeakTimingChain(backend)
    frames = []
    for ob in observations:
        slot = front.push(ob)
        if slot is not None: frames.append(chain.step(slot))
    return dict(vectors=backend.vectors, frames=frames, counts=front.audit())
