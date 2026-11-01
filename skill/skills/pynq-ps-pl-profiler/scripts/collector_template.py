#!/usr/bin/env python3
"""Bounded manual timing collector and host-only demo; Python 3.10+, stdlib."""
import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_phases import ensure_new_outputs, write_new_json
from workloads import WORKLOADS, canonical_hash, make_inputs


class CapacityError(RuntimeError):
    """Stop recording before fixed storage would overflow; nothing is overwritten."""


@dataclass(slots=True)
class SpanSlot:
    phase: str = ""
    parent: int | None = None
    start: int = 0
    end: int | None = None


@dataclass(slots=True)
class TaskSlot:
    sequence: int = 0
    generation: str = "0"
    record_id: str = ""
    input_sha256: str = ""
    wall_start: int = 0
    wall_end: int | None = None
    cpu_start: int = 0
    cpu_end: int | None = None
    valid: bool | None = None
    error: str | None = None
    used_spans: int = 0
    spans: list = field(default_factory=list)


class BoundedCollector:
    """Construct and preallocate before timing; call export only after collection."""
    def __init__(self, capacity, max_spans_per_task=0, wall_clock=time.perf_counter_ns,
                 cpu_clock=time.process_time_ns):
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ValueError("capacity must be a positive integer")
        if isinstance(max_spans_per_task, bool) or not isinstance(max_spans_per_task, int) or max_spans_per_task < 0:
            raise ValueError("max_spans_per_task must be a nonnegative integer")
        self.slots = [TaskSlot(spans=[SpanSlot() for _ in range(max_spans_per_task)]) for _ in range(capacity)]
        self.used = 0
        self.active = None
        self.wall_clock = wall_clock
        self.cpu_clock = cpu_clock
        self.rejected_tasks = 0
        self.rejected_spans = 0

    def begin_task(self, sequence, record_id, input_sha256, generation="0"):
        if self.active is not None:
            raise RuntimeError("a task is already active")
        if self.used == len(self.slots):
            self.rejected_tasks += 1
            raise CapacityError("task capacity exhausted; stop the run and export")
        slot = self.slots[self.used]
        slot.sequence = sequence
        slot.generation = generation
        slot.record_id = record_id
        slot.input_sha256 = input_sha256
        self.active = slot
        self.used += 1
        # Wall encloses both CPU clock reads. CPU does not include the wall reads.
        slot.wall_start = self.wall_clock()
        slot.cpu_start = self.cpu_clock()

    def begin_span(self, phase, parent=None):
        slot = self.active
        if slot is None:
            raise RuntimeError("begin_task is required")
        if slot.used_spans == len(slot.spans):
            self.rejected_spans += 1
            raise CapacityError("span capacity exhausted; finish task invalid and stop the run")
        if parent is not None and (isinstance(parent, bool) or not isinstance(parent, int) or not 0 <= parent < slot.used_spans or slot.spans[parent].end is not None):
            raise ValueError("parent must be a currently open span index")
        index = slot.used_spans
        span = slot.spans[index]
        span.phase = phase
        span.parent = parent
        span.start = self.wall_clock()
        slot.used_spans += 1
        return index

    def end_span(self, index):
        slot = self.active
        if slot is None or isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < slot.used_spans:
            raise ValueError("unknown span index")
        span = slot.spans[index]
        if span.end is not None:
            raise ValueError("span already ended")
        # Close children first so exported intervals can be interpreted as nesting.
        for child_index in range(slot.used_spans):
            child = slot.spans[child_index]
            if child.parent == index and child.end is None:
                raise ValueError("close child spans first")
        span.end = self.wall_clock()

    def end_task(self, valid=True, error=None):
        slot = self.active
        if slot is None:
            raise RuntimeError("no active task")
        slot.cpu_end = self.cpu_clock()
        slot.wall_end = self.wall_clock()
        for index in range(slot.used_spans):
            if slot.spans[index].end is None:
                # Incomplete spans retain presence without invented end timestamps.
                valid = False
                error = error or "unclosed_span"
                break
        slot.valid = valid
        slot.error = error
        self.active = None

    def export(self):
        if self.active is not None:
            raise RuntimeError("end the active task before export")
        records = []
        for slot in self.slots[:self.used]:
            spans, incomplete = [], []
            for index, span in enumerate(slot.spans[:slot.used_spans]):
                item = {"id": str(index), "phase": span.phase, "clock": "host_wall",
                        "parent": str(span.parent) if span.parent is not None else None,
                        "start": span.start, "end": span.end}
                if span.end is None:
                    incomplete.append(item)
                else:
                    spans.append(item)
            records.append({"sequence": slot.sequence, "generation": slot.generation,
                            "record_id": slot.record_id, "input_sha256": slot.input_sha256,
                            "valid": slot.valid, "error": slot.error,
                            "wall": {"clock": "host_wall", "start": slot.wall_start, "end": slot.wall_end},
                            "cpu": {"clock": "host_cpu", "start": slot.cpu_start, "end": slot.cpu_end},
                            "spans": spans, "incomplete_spans": incomplete})
        return records

    def metadata(self):
        return {"capacity": len(self.slots), "recorded_tasks": self.used,
                "rejected_tasks": self.rejected_tasks, "rejected_spans": self.rejected_spans,
                "export_outside_timed_region": True}


HOST_CLOCKS = {
    "host_wall": {"kind": "monotonic_wall", "unit": "ns", "source": "time.perf_counter_ns",
                  "scope": "this host process; one uninterrupted demo invocation"},
    "host_cpu": {"kind": "process_cpu", "unit": "ns", "source": "time.process_time_ns",
                 "scope": "this process; all its threads, excluding child processes"},
}


def collect_demo(count=12, vector_size=64, workload_name="vector_energy", mode="normal_timing"):
    inputs = make_inputs(count, vector_size)
    specifications = [(i, f"input-{i}", canonical_hash(data)) for i, data in enumerate(inputs)]
    workload = {"name": workload_name, "version": "1", "input_set_sha256": canonical_hash(inputs)}
    config = {"vector_size": vector_size, "numeric_type": "python_int", "workers": 1,
              "task_model": "serial", "collector_cpu_clock": "process_time_ns"}
    reference, candidate = WORKLOADS[workload_name]
    runs, output_sets = [], {}
    schedule = [("A1", reference), ("B1", candidate), ("B2", candidate), ("A2", reference)] if mode == "normal_timing" else [("profile", candidate)]
    for name, kernel in schedule:
        collector = BoundedCollector(count, 1 if mode == "phase_profile" else 0)
        results = [None] * count
        for index, data in enumerate(inputs):
            sequence, record_id, input_hash = specifications[index]
            collector.begin_task(sequence, record_id, input_hash)
            try:
                span = collector.begin_span("ps_compute") if mode == "phase_profile" else None
                results[index] = kernel(data)
                if span is not None:
                    collector.end_span(span)
            except Exception as exc:
                collector.end_task(False, type(exc).__name__)
                # Preserve the failed task; export still happens after this loop.
            else:
                collector.end_task(True)
        records = collector.export()
        runs.append({"name": name, "implementation": kernel.__name__, "workload": workload,
                     "config": config, "instrumentation": "boundary_only" if mode == "normal_timing" else "phase_spans",
                     "collector": collector.metadata(), "records": records})
        output_sets[name] = {"schema": "pynq_numeric_outputs_v1", "workload": workload, "config": config,
                             "records": [{**{key: record[key] for key in ("sequence", "generation", "record_id", "input_sha256", "valid")},
                                          "values": results[i]} for i, record in enumerate(records)]}
    trace = {"schema": "pynq_ps_pl_trace_v1", "measurement_kind": mode, "provenance": "host_execution",
             "task_hz": 100, "block_sizes": [3, 5], "clocks": HOST_CLOCKS, "runs": runs}
    return trace, output_sets


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--vector-size", type=int, default=64)
    parser.add_argument("--workload", choices=WORKLOADS, default="vector_energy")
    parser.add_argument("--mode", choices=("normal_timing", "phase_profile"), default="normal_timing")
    args = parser.parse_args(argv)
    names = ("A1", "B1", "B2", "A2") if args.mode == "normal_timing" else ("profile",)
    destinations = {name: args.output.with_name(args.output.stem + f"-outputs-{name}.json") for name in names}
    try:
        ensure_new_outputs([args.output, *destinations.values()])
        trace, outputs = collect_demo(args.count, args.vector_size, args.workload, args.mode)
        write_new_json(args.output, trace)
        for name, values in outputs.items():
            write_new_json(destinations[name], values)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Recorded {args.count} tasks per run; exported {args.output}. Host demo only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
