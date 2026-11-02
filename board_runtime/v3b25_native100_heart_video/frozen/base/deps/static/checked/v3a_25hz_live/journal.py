"""Raw flush uses the frozen journal; results explicitly describe 25 Hz slots."""
import csv
from dataclasses import asdict

from heart_v3a.live.contracts import LIVE_RAW_FIELDS
from heart_v3a.live.journal import LiveJournal, RESULT_FIELDS

SLOT_FIELDS = ('source_first', 'source_last', 'source_first_time_s', 'source_last_time_s',
               'available_time_s', 'signal_time_s', 'support_first', 'support_last',
               'support_first_time_s', 'support_last_time_s', 'generation', 'slot_valid',
               'slot_contact_ready', 'slot_reason', 'first_read_completed_ns', 'first_raw_saved_ns',
               'publication_allowed', 'publication_bpm', 'publication_reason')


class SlotJournal(LiveJournal):
    def open(self):
        if self._opened:
            raise RuntimeError('记录器不能重复打开')
        self.paths.directory.mkdir(parents=True, exist_ok=False)
        self._opened = True
        try:
            self._raw_stream = self.paths.raw_csv.open('x', encoding='utf8', newline='')
            self._result_stream = self.paths.results_csv.open('x', encoding='utf8', newline='')
            self._event_stream = self.paths.events_jsonl.open('x', encoding='utf8', newline='')
            self._raw_writer = csv.DictWriter(self._raw_stream, fieldnames=LIVE_RAW_FIELDS, lineterminator='\n')
            self._result_writer = csv.DictWriter(self._result_stream, fieldnames=RESULT_FIELDS+SLOT_FIELDS, lineterminator='\n')
            self._raw_writer.writeheader()
            self._result_writer.writeheader()
            self._raw_stream.flush()
            self._result_stream.flush()
        except Exception:
            self.close()
            raise
        return self.paths

    def save_result(self, result):
        runtime = asdict(result.runtime)
        row = runtime.pop('frame')
        row.update(runtime)
        saved, first, slot = result.saved, result.pair[0], result.slot
        support_seq = slot.support_sequences or (None, None)
        support_times = slot.support_times or (None, None)
        row.update(ppg_read_completed_ns=saved.record.read_completed_ns, raw_saved_ns=saved.raw_saved_ns,
            process_enqueued_ns=saved.process_enqueued_ns, processing_started_ns=result.processing_started_ns,
            processing_finished_ns=result.processing_finished_ns, pl_call_ns=result.pl_call_ns,
            result_enqueued_ns=result.result_enqueued_ns,
            processing_queue_wait_ns=result.processing_started_ns-saved.process_enqueued_ns,
            result_queue_wait_ns=self.clock.monotonic_ns()-result.result_enqueued_ns,
            read_to_result_ns=result.processing_finished_ns-saved.record.read_completed_ns,
            ps_processing_ns=result.processing_finished_ns-result.processing_started_ns-result.pl_call_ns,
            source_first=slot.source_sequences[0], source_last=slot.source_sequences[1],
            source_first_time_s=slot.source_times[0], source_last_time_s=slot.source_times[1],
            available_time_s=slot.available_time_s, signal_time_s=slot.signal_time_s,
            support_first=support_seq[0], support_last=support_seq[1],
            support_first_time_s=support_times[0], support_last_time_s=support_times[1],
            generation=slot.generation, slot_valid=slot.valid, slot_contact_ready=slot.contact_ready,
            slot_reason=slot.reason, first_read_completed_ns=first.record.read_completed_ns,
            first_raw_saved_ns=first.raw_saved_ns, publication_allowed=result.publication_allowed,
            publication_bpm=result.publication_bpm, publication_reason=result.publication_reason)
        self._counts['results_attempted'] += 1
        self._result_writer.writerow(row)
        self._result_stream.flush()
        self._counts['results_saved'] += 1
