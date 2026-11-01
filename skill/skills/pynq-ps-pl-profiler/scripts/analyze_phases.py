#!/usr/bin/env python3
"""Analyze explicitly clocked serial-task timing; Python 3.10+, stdlib only."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys

SCHEMA = "pynq_ps_pl_trace_v1"
RUNS = ["A1", "B1", "B2", "A2"]
KINDS = {"monotonic_wall", "process_cpu", "thread_cpu", "pl_cycles"}


def finite(value, label, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(f"{label} must be finite and {'positive' if positive else 'nonnegative'}")
    return value


def integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def digest(value, label):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{label} must be lowercase SHA-256 hex")
    return value


def load_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    def parse_float(value):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError(f"nonfinite JSON number: {value}")
        return parsed
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=pairs,
                      parse_constant=constant, parse_float=parse_float)


def ensure_new_outputs(paths):
    """Check the entire requested output set before any work or file creation."""
    identities = set()
    for path in paths:
        path = Path(path)
        identity = os.path.normcase(str(path.resolve()))
        if identity in identities:
            raise ValueError(f"duplicate output destination: {path}")
        identities.add(identity)
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"output already exists; choose a new path: {path}")
        if not path.parent.is_dir():
            raise FileNotFoundError(f"output parent directory does not exist: {path.parent}")


def write_new_json(path, value):
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    # Exclusive creation also closes the race between preflight and writing.
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)


def validate_clocks(clocks):
    if not isinstance(clocks, dict) or not clocks:
        raise ValueError("clocks must be a nonempty object")
    for clock_id, clock in clocks.items():
        nonempty(clock_id, "clock ID")
        if not isinstance(clock, dict) or clock.get("kind") not in KINDS:
            raise ValueError(f"unknown clock kind: {clock_id}")
        nonempty(clock.get("source"), "clock source")
        nonempty(clock.get("scope"), "clock scope")
        unit = "cycles" if clock["kind"] == "pl_cycles" else "ns"
        if clock.get("unit") != unit:
            raise ValueError(f"clock {clock_id} must use {unit}")
        hz, source = clock.get("frequency_hz"), clock.get("frequency_source")
        if hz is not None or source is not None:
            if clock["kind"] != "pl_cycles":
                raise ValueError("only PL cycle clocks carry frequency_hz")
            finite(hz, "PL frequency_hz", positive=True)
            nonempty(source, "PL frequency_source")


def interval(item, clocks, label, allowed=None):
    if not isinstance(item, dict) or item.get("clock") not in clocks:
        raise ValueError(f"{label} requires a declared clock")
    clock = clocks[item["clock"]]
    if allowed and clock["kind"] not in allowed:
        raise ValueError(f"wrong clock kind for {label}")
    start = integer(item.get("start"), f"{label}.start")
    end = integer(item.get("end"), f"{label}.end")
    if end < start:
        raise ValueError(f"{label} ends before it starts")
    return end - start


def stats(values):
    if not values:
        return {"count": 0, "mean": None, "p50": None, "p95": None, "p99": None, "max": None}
    ordered = sorted(values)
    result = {"count": len(values), "mean": statistics.fmean(values), "max": max(values)}
    for p in (50, 95, 99):
        result[f"p{p}"] = ordered[max(0, math.ceil(len(ordered) * p / 100) - 1)]
    return result


def scaled_duration(ticks, clock):
    if clock["unit"] == "ns":
        return ticks
    return ticks * 1e9 / clock["frequency_hz"] if clock.get("frequency_hz") else None


def analyze_spans(record, clocks):
    spans = record.get("spans", [])
    if not isinstance(spans, list):
        raise ValueError("spans must be a list")
    by_id = {}
    wall = record["wall"]
    for span in spans:
        if not isinstance(span, dict):
            raise ValueError("each span must be an object")
        sid = nonempty(span.get("id"), "span.id")
        if sid in by_id:
            raise ValueError("duplicate span ID in record")
        nonempty(span.get("phase"), "span.phase")
        interval(span, clocks, "span")
        if span["clock"] == wall["clock"] and not (wall["start"] <= span["start"] <= span["end"] <= wall["end"]):
            raise ValueError("same-clock span lies outside task wall interval")
        by_id[sid] = span
    ancestors = {}
    for sid, span in by_id.items():
        seen = {sid}
        chain = set()
        cursor = span
        while cursor.get("parent") is not None:
            parent_id = cursor["parent"]
            if parent_id not in by_id or parent_id in seen:
                raise ValueError("span parent is missing or cyclic")
            parent = by_id[parent_id]
            if parent["clock"] != cursor["clock"]:
                raise ValueError("parent and child must use the identical clock domain")
            if not parent["start"] <= cursor["start"] <= cursor["end"] <= parent["end"]:
                raise ValueError("child span is not contained in parent")
            seen.add(parent_id)
            chain.add(parent_id)
            cursor = parent
        ancestors[sid] = chain

    wall_spans = [s for s in spans if s["clock"] == wall["clock"]]
    boundaries = sorted({wall["start"], wall["end"], *[x for s in wall_spans for x in (s["start"], s["end"])]})
    exclusive = {}
    unknown = ambiguous = 0
    for start, end in zip(boundaries, boundaries[1:]):
        active = [s for s in wall_spans if s["start"] <= start and s["end"] >= end]
        if not active:
            unknown += end - start
            continue
        leaves = [s for s in active if not any(s["id"] in ancestors[other["id"]] for other in active)]
        if len(leaves) != 1:
            ambiguous += end - start
        else:
            phase = leaves[0]["phase"]
            exclusive[phase] = exclusive.get(phase, 0) + end - start
    inclusive = []
    for span in spans:
        ticks = span["end"] - span["start"]
        inclusive.append({"id": span["id"], "phase": span["phase"], "clock": span["clock"],
                          "duration_ticks": ticks, "duration_ns": scaled_duration(ticks, clocks[span["clock"]]),
                          "used_for_wall_attribution": span["clock"] == wall["clock"]})
    return {"exclusive_phase_ns": exclusive, "unknown_unobserved_ns": unknown,
            "ambiguous_overlap_ns": ambiguous, "inclusive_spans": inclusive}


def analyze_record(record, clocks):
    if not isinstance(record, dict):
        raise ValueError("record must be an object")
    integer(record.get("sequence"), "sequence")
    nonempty(record.get("generation"), "generation")
    nonempty(record.get("record_id"), "record_id")
    digest(record.get("input_sha256"), "input_sha256")
    if record.get("valid") not in (True, False, None) or (record.get("valid") is not None and not isinstance(record["valid"], bool)):
        raise ValueError("valid must be true, false, or null")
    if "valid" not in record:
        raise ValueError("valid is required; use null when unknown")
    wall_ns = interval(record.get("wall"), clocks, "wall", {"monotonic_wall"})
    cpu_ns = interval(record["cpu"], clocks, "cpu", {"process_cpu", "thread_cpu"}) if record.get("cpu") is not None else None
    pl = []
    for sample in record.get("pl_samples", []):
        if not isinstance(sample, dict) or sample.get("clock") not in clocks or clocks[sample["clock"]]["kind"] != "pl_cycles":
            raise ValueError("PL sample requires a declared PL cycle clock")
        nonempty(sample.get("phase"), "PL sample phase")
        cycles = integer(sample.get("cycles"), "PL cycles")
        duration = scaled_duration(cycles, clocks[sample["clock"]])
        pl.append({**sample, "duration_ns": duration,
                   "conversion": "frequency_declared" if duration is not None else "unknown_frequency"})
    return {"wall_ns": wall_ns, "cpu_ns": cpu_ns,
            "cpu_clock": record.get("cpu", {}).get("clock") if record.get("cpu") else None,
            "wall_attribution": analyze_spans(record, clocks), "pl_samples": pl}


def contiguous_blocks(records, metrics, size, hz):
    windows = []
    segment = []
    for index, record in enumerate(records):
        if segment:
            previous = records[segment[-1]]
            if record["generation"] != previous["generation"] or record["sequence"] != previous["sequence"] + 1:
                segment = []
        segment.append(index)
        segment = segment[-size:]
        if len(segment) != size:
            continue
        selected = [records[i] for i in segment]
        single_clock = len({r["wall"]["clock"] for r in selected}) == 1
        elapsed = selected[-1]["wall"]["end"] - selected[0]["wall"]["start"] if single_clock else None
        summed = sum(metrics[i]["wall_ns"] for i in segment)
        windows.append({"generation": record["generation"], "start_sequence": selected[0]["sequence"],
                        "end_sequence": record["sequence"], "record_ids": [r["record_id"] for r in selected],
                        "elapsed_ns_including_gaps": elapsed, "summed_task_wall_ns": summed,
                        "inter_task_gaps_ns": elapsed - summed if elapsed is not None else None,
                        "valid_false": sum(r["valid"] is False for r in selected),
                        "valid_unknown": sum(r["valid"] is None for r in selected)})
    known = [w for w in windows if w["elapsed_ns_including_gaps"] is not None]
    budget = size * 1e9 / hz
    return {"size": size, "nominal_budget_ns": budget, "window_count": len(windows),
            "unknown_elapsed_windows": len(windows) - len(known),
            "over_nominal_budget": sum(w["elapsed_ns_including_gaps"] > budget for w in known),
            "worst": max(known, key=lambda w: w["elapsed_ns_including_gaps"]) if known else None,
            "elapsed_stats_ns": stats([w["elapsed_ns_including_gaps"] for w in known]), "windows": windows}


def analyze_run(run, clocks, hz, sizes, kind):
    nonempty(run.get("name"), "run.name")
    nonempty(run.get("implementation"), "run.implementation")
    if not isinstance(run.get("workload"), dict) or not run["workload"]:
        raise ValueError("run workload must be a nonempty object identifying version and input set")
    nonempty(run["workload"].get("name"), "workload.name")
    nonempty(run["workload"].get("version"), "workload.version")
    digest(run["workload"].get("input_set_sha256"), "workload.input_set_sha256")
    if not isinstance(run.get("config"), dict) or not run["config"]:
        raise ValueError("run config must declare the measurement configuration")
    if run.get("instrumentation") != ("boundary_only" if kind == "normal_timing" else "phase_spans"):
        raise ValueError("instrumentation does not match measurement_kind")
    records = run.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("each run requires nonempty records")
    seen_ids, seen_generations = set(), set()
    previous = None
    metrics = []
    for record in records:
        result = analyze_record(record, clocks)
        identity = (record["generation"], record["record_id"])
        if identity in seen_ids:
            raise ValueError("record ID repeats within generation")
        seen_ids.add(identity)
        if kind == "normal_timing" and (record.get("spans") or record.get("pl_samples")):
            raise ValueError("ordinary timing cannot include phase spans or PL probe samples")
        gap = None
        if previous:
            same_generation = record["generation"] == previous["generation"]
            if same_generation and record["sequence"] <= previous["sequence"]:
                raise ValueError("sequence repeats or regresses within generation")
            if not same_generation and record["generation"] in seen_generations:
                raise ValueError("generation reappears after another generation")
            if record["wall"]["clock"] == previous["wall"]["clock"]:
                gap = record["wall"]["start"] - previous["wall"]["end"]
                if gap < 0:
                    raise ValueError("serial task wall intervals overlap or regress")
        seen_generations.add(record["generation"])
        result["gap_before_ns"] = gap
        result["gap_before_reason"] = ("first_record" if previous is None else
                                       "measured_same_clock" if gap is not None else "unknown_clock_domain")
        result["record"] = record
        metrics.append(result)
        previous = record
    phases = {}
    for item in metrics:
        for name, value in item["wall_attribution"]["exclusive_phase_ns"].items():
            phases[name] = phases.get(name, 0) + value
    cpu_by_clock = {}
    for item in metrics:
        if item["cpu_ns"] is not None:
            cpu_by_clock.setdefault(item["cpu_clock"], []).append(item["cpu_ns"])
    complete_gap_measurement = all(m["gap_before_ns"] is not None for m in metrics[1:])
    return {"name": run["name"], "implementation": run["implementation"], "workload": run["workload"],
            "config": run["config"], "instrumentation": run["instrumentation"],
            "collector": run.get("collector"), "count": len(records), "first_record_retained": True,
            "valid_true": sum(r["valid"] is True for r in records),
            "valid_false": sum(r["valid"] is False for r in records),
            "valid_unknown": sum(r["valid"] is None for r in records),
            "wall_ns": stats([m["wall_ns"] for m in metrics]),
            "cpu_ns_by_clock": {clock: stats(values) for clock, values in cpu_by_clock.items()},
            "over_task_period": sum(m["wall_ns"] > 1e9 / hz for m in metrics),
            "inter_task_gaps_ns": stats([m["gap_before_ns"] for m in metrics if m["gap_before_ns"] is not None]),
            "complete_elapsed_ns": sum(m["wall_ns"] for m in metrics) + sum(m["gap_before_ns"] or 0 for m in metrics) if complete_gap_measurement else None,
            "exclusive_phase_totals_ns": phases,
            "unknown_unobserved_ns": sum(m["wall_attribution"]["unknown_unobserved_ns"] for m in metrics),
            "ambiguous_overlap_ns": sum(m["wall_attribution"]["ambiguous_overlap_ns"] for m in metrics),
            "blocks": [contiguous_blocks(records, metrics, size, hz) for size in sizes], "records": metrics}


def record_keys(run):
    return [(r["generation"], r["sequence"], r["record_id"], r["input_sha256"], r["valid"]) for r in run["records"]]


def abba_comparison(trace, summaries):
    runs = trace["runs"]
    reasons = []
    if trace["measurement_kind"] != "normal_timing":
        reasons.append("phase_profile_is_not_ordinary_timing")
    if [r["name"] for r in runs] != RUNS:
        reasons.append("requires_ordered_A1_B1_B2_A2")
    if reasons:
        return {"eligible": False, "reasons": reasons, "mean_wall_reduction_percent": None}
    baseline = runs[0]
    for field in ("workload", "config"):
        if any(r[field] != baseline[field] for r in runs[1:]):
            reasons.append(f"different_{field}")
    if any(record_keys(r) != record_keys(baseline) for r in runs[1:]):
        reasons.append("different_record_keys_inputs_or_validity")
    # The declared source/scope of the wall timer must also match for every task.
    clock_keys = lambda r: [r0["wall"]["clock"] for r0 in r["records"]]
    if any(clock_keys(r) != clock_keys(baseline) for r in runs[1:]):
        reasons.append("different_wall_clock_domains")
    if runs[0]["implementation"] != runs[3]["implementation"] or runs[1]["implementation"] != runs[2]["implementation"]:
        reasons.append("implementation_changed_inside_arm")
    if any(r.get("collector", {}).get("rejected_tasks", 0) or r.get("collector", {}).get("rejected_spans", 0) for r in runs):
        reasons.append("collector_capacity_exceeded")
    if reasons:
        return {"eligible": False, "reasons": reasons, "mean_wall_reduction_percent": None}
    a = statistics.fmean(m["wall_ns"] for i in (0, 3) for m in summaries[i]["records"])
    b = statistics.fmean(m["wall_ns"] for i in (1, 2) for m in summaries[i]["records"])
    return {"eligible": True, "reasons": [], "baseline_mean_wall_ns": a,
            "candidate_mean_wall_ns": b, "mean_wall_reduction_percent": (a - b) / a * 100 if a else None,
            "invalid_or_unknown_records_retained": sum(r["valid"] is not True for run in runs for r in run["records"]),
            "interpretation": "Timing description only; numerical equivalence and hardware acceptance are separate."}


def analyze(trace, task_hz=None, block_sizes=None):
    if not isinstance(trace, dict) or trace.get("schema") != SCHEMA:
        raise ValueError(f"schema must be {SCHEMA}")
    if trace.get("measurement_kind") not in {"normal_timing", "phase_profile"}:
        raise ValueError("measurement_kind must be normal_timing or phase_profile")
    if trace.get("provenance") not in {"synthetic", "host_execution", "board_execution"}:
        raise ValueError("provenance must be synthetic, host_execution, or board_execution")
    clocks = trace.get("clocks")
    validate_clocks(clocks)
    hz = finite(task_hz if task_hz is not None else trace.get("task_hz"), "task_hz", positive=True)
    sizes = block_sizes if block_sizes is not None else trace.get("block_sizes")
    if not isinstance(sizes, list) or not sizes or any(integer(n, "block_size") == 0 for n in sizes):
        raise ValueError("block_sizes must be a nonempty list of positive integers")
    if len(set(sizes)) != len(sizes):
        raise ValueError("block_sizes must be unique")
    runs = trace.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("runs must be a nonempty list")
    summaries = [analyze_run(run, clocks, hz, sizes, trace["measurement_kind"]) for run in runs]
    if len({r["name"] for r in runs}) != len(runs):
        raise ValueError("run names must be unique")
    return {"schema": "pynq_ps_pl_summary_v1", "measurement_kind": trace["measurement_kind"],
            "provenance": trace["provenance"], "clocks": clocks, "task_hz": hz, "block_sizes": sizes,
            "nominal_task_period_ns": 1e9 / hz, "runs": summaries, "abba": abba_comparison(trace, summaries),
            "numerical_equivalence": "not_evaluated", "hardware_acceptance": "not_evaluated",
            "attribution_rule": "Only measured spans on the exact task wall clock are attributed; all other time is unknown or overlap-ambiguous. CPU and PL domains stay independent."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--task-hz", type=float)
    parser.add_argument("--block-sizes", type=int, nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.output:
            ensure_new_outputs([args.output])
        result = analyze(load_json(args.trace), args.task_hz, args.block_sizes)
        result["input_sha256"] = hashlib.sha256(args.trace.read_bytes()).hexdigest()
        if args.output:
            write_new_json(args.output, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
