#!/usr/bin/env python3
"""Generate deterministic timing fixtures, never measured hardware evidence."""
import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_phases import ensure_new_outputs, write_new_json
from workloads import canonical_hash, make_inputs


def synthetic_trace(kind="phase_profile", count=6):
    inputs = make_inputs(count, 16)
    clocks = {
        "wall": {"kind": "monotonic_wall", "unit": "ns", "source": "synthetic integer timeline",
                 "scope": "synthetic host wall domain"},
        "cpu": {"kind": "process_cpu", "unit": "ns", "source": "synthetic process CPU counter",
                "scope": "synthetic one-process CPU domain"},
        "pl": {"kind": "pl_cycles", "unit": "cycles", "source": "synthetic IP cycle counter",
               "scope": "synthetic IP; 64-bit already-unwrapped counter", "frequency_hz": 100000000,
               "frequency_source": "synthetic fixture declaration, not a measured clock"},
    }
    workload = {"name": "vector_energy", "version": "1", "input_set_sha256": canonical_hash(inputs)}
    config = {"vector_size": 16, "numeric_type": "python_int", "workers": 1, "task_model": "serial"}
    names = ["profile"] if kind == "phase_profile" else ["A1", "B1", "B2", "A2"]
    runs = []
    for run_index, name in enumerate(names):
        records = []
        start = run_index * 1000000
        for sequence, values in enumerate(inputs):
            duration = 750 if name.startswith("B") else 1000
            record = {"sequence": sequence, "generation": "0", "record_id": f"vector-{sequence}",
                      "input_sha256": canonical_hash(values), "valid": sequence != 2,
                      "wall": {"clock": "wall", "start": start, "end": start + duration},
                      "cpu": {"clock": "cpu", "start": sequence * 500, "end": sequence * 500 + 300}}
            if kind == "phase_profile":
                definitions = [
                    ("prepare", "ps_prepare", None, 0, 80),
                    ("call", "c_call", None, 100, 800),
                    ("ipc", "ipc", "call", 120, 200),
                    ("wait", "pl_wait", "call", 200, 700),
                    ("return", "c_return", "call", 700, 750),
                    ("finish", "ps_finish", None, 850, 950),
                ]
                record["spans"] = [{"id": sid, "phase": phase, "parent": parent, "clock": "wall",
                                    "start": start + lo, "end": start + hi} for sid, phase, parent, lo, hi in definitions]
                record["pl_samples"] = [{"phase": "pl_kernel", "clock": "pl", "cycles": 25}]
            records.append(record)
            start += duration + (4000 if sequence == 2 else 100)
        runs.append({"name": name, "implementation": "candidate" if name.startswith("B") else "reference",
                     "workload": copy.deepcopy(workload), "config": copy.deepcopy(config),
                     "instrumentation": "phase_spans" if kind == "phase_profile" else "boundary_only", "records": records})
    return {"schema": "pynq_ps_pl_trace_v1", "measurement_kind": kind, "provenance": "synthetic",
            "task_hz": 500000, "block_sizes": [2, 3, 5], "clocks": clocks, "runs": runs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        destinations = {kind: args.output_dir / f"synthetic_{kind}.json" for kind in ("phase_profile", "normal_timing")}
        ensure_new_outputs(list(destinations.values()))
        for kind, path in destinations.items():
            write_new_json(path, synthetic_trace(kind))
            print(path)
        return 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
