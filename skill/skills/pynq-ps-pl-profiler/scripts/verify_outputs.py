#!/usr/bin/env python3
"""Compare saved numeric records separately from timing; stdlib only."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_phases import digest, ensure_new_outputs, finite, integer, load_json, nonempty, write_new_json


def validate(document):
    if not isinstance(document, dict) or document.get("schema") != "pynq_numeric_outputs_v1":
        raise ValueError("numeric output schema must be pynq_numeric_outputs_v1")
    if not isinstance(document.get("workload"), dict) or not document["workload"] or not isinstance(document.get("config"), dict) or not document["config"]:
        raise ValueError("workload and config must be nonempty objects")
    records = document.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("numeric records must be nonempty")
    keys = []
    for record in records:
        integer(record.get("sequence"), "sequence")
        nonempty(record.get("generation"), "generation")
        nonempty(record.get("record_id"), "record_id")
        digest(record.get("input_sha256"), "input_sha256")
        if "valid" not in record or (record["valid"] is not None and not isinstance(record["valid"], bool)):
            raise ValueError("valid must be true, false, or null")
        values = record.get("values")
        if values is None and record["valid"] is not True:
            values = []
        elif not isinstance(values, list) or not values:
            raise ValueError("valid output values must be a nonempty list")
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in values):
            raise ValueError("output values must be finite real numbers")
        keys.append(tuple(record[k] for k in ("generation", "sequence", "record_id", "input_sha256", "valid")))
    if len(set((key[0], key[1]) for key in keys)) != len(keys) or len(set((key[0], key[2]) for key in keys)) != len(keys):
        raise ValueError("numeric record identity repeats")
    return keys


def compare(left, right, atol, rtol):
    finite(atol, "atol")
    finite(rtol, "rtol")
    left_keys, right_keys = validate(left), validate(right)
    differences = [field for field in ("workload", "config") if left[field] != right[field]]
    if left_keys != right_keys:
        differences.append("ordered_record_keys_inputs_or_validity")
    if differences:
        return {"status": "incomparable", "differences": differences, "atol": atol, "rtol": rtol}
    rows = []
    for a, b in zip(left["records"], right["records"]):
        av, bv = a.get("values"), b.get("values")
        if a["valid"] is not True:
            rows.append({"sequence": a["sequence"], "generation": a["generation"], "record_id": a["record_id"],
                         "status": "invalid_or_unknown", "valid": a["valid"]})
            continue
        shape_match = len(av) == len(bv)
        mismatches = [i for i, (x, y) in enumerate(zip(av, bv)) if abs(x - y) > atol + rtol * abs(x)] if shape_match else []
        rows.append({"sequence": a["sequence"], "generation": a["generation"], "record_id": a["record_id"],
                     "status": "pass" if shape_match and not mismatches else "fail", "shape_match": shape_match,
                     "mismatch_indices": mismatches, "max_abs_error": max((abs(x - y) for x, y in zip(av, bv)), default=None) if shape_match else None})
    statuses = [row["status"] for row in rows]
    status = "fail" if "fail" in statuses else "incomplete" if "invalid_or_unknown" in statuses else "pass"
    return {"status": status, "atol": atol, "rtol": rtol, "tolerance_rule": "abs(reference-candidate) <= atol + rtol*abs(reference)",
            "record_count": len(rows), "records": rows, "timing_and_hardware_acceptance": "not_evaluated"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--atol", required=True, type=float)
    parser.add_argument("--rtol", required=True, type=float)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output:
            ensure_new_outputs([args.output])
        result = compare(load_json(args.reference), load_json(args.candidate), args.atol, args.rtol)
        if args.output:
            write_new_json(args.output, result)
        else:
            print(json.dumps(result, indent=2, allow_nan=False))
        return {"pass": 0, "fail": 1, "incomplete": 2, "incomparable": 2}[result["status"]]
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
