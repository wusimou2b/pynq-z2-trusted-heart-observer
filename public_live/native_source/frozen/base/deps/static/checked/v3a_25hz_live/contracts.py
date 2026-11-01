from dataclasses import dataclass

from heart_v3a.live.contracts import SavedRecord
from heart_v3a.runtime_pl_chain import PlRuntimeFrame
from v3a_rate25.frontend import Slot


@dataclass(frozen=True)
class ProcessedSlot:
    pair: tuple[SavedRecord, SavedRecord]
    slot: Slot
    runtime: PlRuntimeFrame
    processing_started_ns: int
    processing_finished_ns: int
    pl_call_ns: int
    result_enqueued_ns: int
    publication_allowed: bool = False
    publication_bpm: float | None = None
    publication_reason: str = ''

    @property
    def saved(self):
        """Newest raw record: legacy read-to-result clock, not FIR centre time."""
        return self.pair[-1]
