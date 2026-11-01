"""Behavioral checks for clock/attribution, retained records, ABBA, and collection."""
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from analyze_phases import analyze, load_json
from collector_template import BoundedCollector, CapacityError, collect_demo
from make_synthetic import synthetic_trace
from verify_outputs import compare
from workloads import WORKLOADS, canonical_hash, make_inputs


class PhaseTests(unittest.TestCase):
    def test_nested_spans_do_not_double_count(self):
        result = analyze(synthetic_trace())
        record = result["runs"][0]["records"][0]
        attr = record["wall_attribution"]
        self.assertEqual(attr["exclusive_phase_ns"]["c_call"], 70)
        self.assertEqual(attr["exclusive_phase_ns"]["ipc"], 80)
        self.assertEqual(attr["exclusive_phase_ns"]["c_return"], 50)
        self.assertEqual(attr["unknown_unobserved_ns"], 120)
        self.assertEqual(sum(attr["exclusive_phase_ns"].values()) + attr["unknown_unobserved_ns"] + attr["ambiguous_overlap_ns"], record["wall_ns"])

    def test_sibling_overlap_is_ambiguous_once(self):
        trace = synthetic_trace()
        trace["runs"][0]["records"][0]["spans"].append({"id": "overlap", "phase": "diagnostic", "parent": "call", "clock": "wall", "start": 150, "end": 250})
        attr = analyze(trace)["runs"][0]["records"][0]["wall_attribution"]
        self.assertEqual(attr["ambiguous_overlap_ns"], 100)
        self.assertEqual(sum(attr["exclusive_phase_ns"].values()) + attr["unknown_unobserved_ns"] + attr["ambiguous_overlap_ns"], 1000)

    def test_absent_spans_and_cpu_do_not_infer_gil_or_ipc(self):
        trace = synthetic_trace()
        record = trace["runs"][0]["records"][0]
        record["spans"] = []
        record.pop("cpu")
        result = analyze(trace)["runs"][0]["records"][0]
        self.assertIsNone(result["cpu_ns"])
        self.assertEqual(result["wall_attribution"]["unknown_unobserved_ns"], 1000)
        self.assertEqual(result["wall_attribution"]["exclusive_phase_ns"], {})

    def test_cpu_longer_than_wall_is_independent(self):
        trace = synthetic_trace()
        trace["runs"][0]["records"][0]["cpu"]["end"] = 2000
        record = analyze(trace)["runs"][0]["records"][0]
        self.assertEqual(record["cpu_ns"], 2000)
        self.assertEqual(record["wall_attribution"]["unknown_unobserved_ns"], 120)

    def test_other_clock_span_never_subtracted(self):
        trace = synthetic_trace()
        trace["clocks"]["remote"] = {"kind": "monotonic_wall", "unit": "ns", "source": "remote fake timer", "scope": "different host epoch"}
        trace["runs"][0]["records"][0]["spans"].append({"id": "remote", "phase": "ipc", "clock": "remote", "start": 1000000000, "end": 1000007000})
        attr = analyze(trace)["runs"][0]["records"][0]["wall_attribution"]
        self.assertEqual(attr["exclusive_phase_ns"]["ipc"], 80)
        self.assertEqual(attr["unknown_unobserved_ns"], 120)
        self.assertFalse(attr["inclusive_spans"][-1]["used_for_wall_attribution"])

    def test_cross_clock_parent_rejected(self):
        trace = synthetic_trace()
        trace["runs"][0]["records"][0]["spans"][2]["clock"] = "cpu"
        with self.assertRaisesRegex(ValueError, "identical clock"):
            analyze(trace)

    def test_pl_conversion_needs_frequency_and_source(self):
        trace = synthetic_trace()
        record = analyze(trace)["runs"][0]["records"][0]
        self.assertEqual(record["pl_samples"][0]["duration_ns"], 250)
        trace["clocks"]["pl"].pop("frequency_source")
        with self.assertRaisesRegex(ValueError, "frequency_source"):
            analyze(trace)
        trace["clocks"]["pl"].pop("frequency_hz")
        sample = analyze(trace)["runs"][0]["records"][0]["pl_samples"][0]
        self.assertEqual(sample["cycles"], 25)
        self.assertIsNone(sample["duration_ns"])
        self.assertEqual(sample["conversion"], "unknown_frequency")

    def test_malformed_nested_spans_rejected(self):
        for mutation in ("outside", "cycle", "duplicate"):
            with self.subTest(mutation=mutation):
                trace = synthetic_trace()
                spans = trace["runs"][0]["records"][0]["spans"]
                if mutation == "outside":
                    spans[2]["end"] = 900
                elif mutation == "cycle":
                    spans[1]["parent"] = "ipc"
                else:
                    spans.append(copy.deepcopy(spans[0]))
                with self.assertRaises(ValueError):
                    analyze(trace)


class RecordAndBlockTests(unittest.TestCase):
    def test_first_invalid_and_gap_retained(self):
        run = analyze(synthetic_trace())["runs"][0]
        self.assertEqual([m["record"]["sequence"] for m in run["records"]], list(range(6)))
        self.assertEqual(run["valid_false"], 1)
        self.assertEqual(run["records"][3]["gap_before_ns"], 4000)
        self.assertEqual(run["blocks"][0]["worst"]["elapsed_ns_including_gaps"], 6000)
        self.assertEqual(run["blocks"][0]["worst"]["inter_task_gaps_ns"], 4000)

    def test_sequence_holes_and_generation_changes_split_blocks(self):
        trace = synthetic_trace()
        records = trace["runs"][0]["records"]
        records[2]["sequence"] = 3
        records[3]["sequence"] = 4
        records[4]["generation"] = "1"
        records[4]["sequence"] = 0
        records[5]["generation"] = "1"
        records[5]["sequence"] = 1
        block = analyze(trace, block_sizes=[2])["runs"][0]["blocks"][0]
        self.assertEqual(block["window_count"], 3)
        self.assertEqual([(w["start_sequence"], w["end_sequence"]) for w in block["windows"]], [(0, 1), (3, 4), (0, 1)])

    def test_cross_clock_gaps_and_blocks_unknown(self):
        trace = synthetic_trace()
        trace["clocks"]["wall2"] = {**trace["clocks"]["wall"], "scope": "unrelated epoch"}
        record = trace["runs"][0]["records"][1]
        record["wall"] = {"clock": "wall2", "start": 0, "end": 1000}
        record["spans"] = []
        run = analyze(trace, block_sizes=[2])["runs"][0]
        self.assertIsNone(run["records"][1]["gap_before_ns"])
        self.assertEqual(run["blocks"][0]["unknown_elapsed_windows"], 2)
        self.assertIsNone(run["complete_elapsed_ns"])

    def test_configurable_frequency_and_sizes(self):
        result = analyze(synthetic_trace(), task_hz=250000, block_sizes=[4])
        self.assertEqual(result["nominal_task_period_ns"], 4000)
        self.assertEqual(result["runs"][0]["blocks"][0]["nominal_budget_ns"], 16000)

    def test_nonfinite_and_invalid_frequency_rejected(self):
        for hz in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(hz=hz), self.assertRaises(ValueError):
                analyze(synthetic_trace(), task_hz=hz)

    def test_bad_order_and_overlap_rejected(self):
        for field, value in (("sequence", 0), ("wall", {"clock": "wall", "start": 1, "end": 1001})):
            trace = synthetic_trace()
            trace["runs"][0]["records"][1][field] = value
            with self.assertRaises(ValueError):
                analyze(trace)


class AbbaTests(unittest.TestCase):
    def test_normal_abba_reports_synthetic_timing_only(self):
        result = analyze(synthetic_trace("normal_timing"))
        self.assertTrue(result["abba"]["eligible"])
        self.assertEqual(result["abba"]["mean_wall_reduction_percent"], 25)
        self.assertEqual(result["abba"]["invalid_or_unknown_records_retained"], 4)
        self.assertEqual(result["numerical_equivalence"], "not_evaluated")
        self.assertEqual(result["hardware_acceptance"], "not_evaluated")
        self.assertEqual(result["provenance"], "synthetic")

    def test_profile_cannot_claim_normal_abba(self):
        result = analyze(synthetic_trace())
        self.assertFalse(result["abba"]["eligible"])
        self.assertIsNone(result["abba"]["mean_wall_reduction_percent"])

    def test_identity_config_workload_or_clock_mismatch_denies_comparison(self):
        for what in ("input", "validity", "config", "workload", "clock", "arm", "overflow"):
            with self.subTest(what=what):
                trace = synthetic_trace("normal_timing")
                run = trace["runs"][1]
                if what == "input":
                    run["records"][0]["input_sha256"] = "0" * 64
                elif what == "validity":
                    run["records"][0]["valid"] = None
                elif what == "config":
                    run["config"]["workers"] = 2
                elif what == "workload":
                    run["workload"]["version"] = "2"
                elif what == "clock":
                    trace["clocks"]["other"] = dict(trace["clocks"]["wall"])
                    run["records"][0]["wall"]["clock"] = "other"
                elif what == "arm":
                    run["implementation"] = "changed"
                else:
                    run["collector"] = {"rejected_tasks": 1}
                result = analyze(trace)["abba"]
                self.assertFalse(result["eligible"])
                self.assertIsNone(result["mean_wall_reduction_percent"])

    def test_ordinary_run_rejects_phase_probe(self):
        trace = synthetic_trace("normal_timing")
        trace["runs"][0]["records"][0]["pl_samples"] = [{"phase": "kernel", "clock": "pl", "cycles": 1}]
        with self.assertRaisesRegex(ValueError, "ordinary timing"):
            analyze(trace)


class CollectorAndNumericTests(unittest.TestCase):
    def collector(self, capacity=2, spans=2):
        wall_values = iter(range(0, 100000, 10))
        cpu_values = iter(range(0, 100000, 3))
        return BoundedCollector(capacity, spans, lambda: next(wall_values), lambda: next(cpu_values))

    def test_bounded_collector_refuses_overwrite(self):
        collector = self.collector(capacity=1)
        collector.begin_task(0, "first", "0" * 64)
        collector.end_task(False, "test_failure")
        with self.assertRaises(CapacityError):
            collector.begin_task(1, "second", "1" * 64)
        self.assertEqual(collector.metadata()["rejected_tasks"], 1)
        self.assertEqual(collector.export()[0]["record_id"], "first")
        self.assertFalse(collector.export()[0]["valid"])

    def test_incomplete_span_preserved_without_fabricated_end(self):
        collector = self.collector()
        collector.begin_task(0, "first", "0" * 64)
        collector.begin_span("ps_compute")
        with self.assertRaises(RuntimeError):
            collector.export()
        collector.end_task()
        record = collector.export()[0]
        self.assertFalse(record["valid"])
        self.assertEqual(record["spans"], [])
        self.assertIsNone(record["incomplete_spans"][0]["end"])

    def test_span_capacity_and_nested_completion(self):
        collector = self.collector(spans=2)
        collector.begin_task(0, "first", "0" * 64)
        parent = collector.begin_span("call")
        child = collector.begin_span("compute", parent)
        with self.assertRaises(ValueError):
            collector.end_span(parent)
        with self.assertRaises(CapacityError):
            collector.begin_span("extra")
        collector.end_span(child)
        collector.end_span(parent)
        collector.end_task(False, "span_capacity")
        self.assertEqual(len(collector.export()[0]["spans"]), 2)
        self.assertEqual(collector.metadata()["rejected_spans"], 1)

    def test_both_workloads_match_for_all_records(self):
        inputs = make_inputs(9, 33)
        for name, (reference, candidate) in WORKLOADS.items():
            with self.subTest(workload=name):
                self.assertEqual([reference(x) for x in inputs], [candidate(x) for x in inputs])

    def test_host_demo_analyzes_and_numeric_verification_is_separate(self):
        for name in WORKLOADS:
            trace, outputs = collect_demo(6, 16, name)
            result = analyze(trace)
            self.assertTrue(result["abba"]["eligible"])
            self.assertEqual(result["numerical_equivalence"], "not_evaluated")
            self.assertEqual(compare(outputs["A1"], outputs["B1"], 0, 0)["status"], "pass")
        profile, _ = collect_demo(4, 16, mode="phase_profile")
        self.assertIn("ps_compute", analyze(profile)["runs"][0]["exclusive_phase_totals_ns"])

    def test_numeric_failure_invalid_and_mismatched_records(self):
        _, outputs = collect_demo(4, 16)
        reference = outputs["A1"]
        candidate = copy.deepcopy(outputs["B1"])
        candidate["records"][0]["values"][0] += 1
        self.assertEqual(compare(reference, candidate, 0, 0)["status"], "fail")
        self.assertEqual(compare(reference, candidate, 1, 0)["status"], "pass")
        reference["records"][0]["valid"] = False
        candidate["records"][0]["valid"] = False
        report = compare(reference, candidate, 0, 0)
        self.assertEqual(report["status"], "incomplete")
        self.assertEqual(report["record_count"], 4)
        candidate["config"]["workers"] = 2
        self.assertEqual(compare(reference, candidate, 0, 0)["status"], "incomparable")

    def test_nonfinite_numeric_values_rejected(self):
        _, outputs = collect_demo(3, 16)
        outputs["B1"]["records"][0]["values"][0] = float("nan")
        with self.assertRaises(ValueError):
            compare(outputs["A1"], outputs["B1"], 0, 0)

    def test_duplicate_json_keys_rejected_and_cli_runs_without_cwd_imports(self):
        with tempfile.TemporaryDirectory(prefix="profiler-test-", dir=ROOT) as directory:
            root = Path(directory)
            malformed = root / "bad.json"
            malformed.write_text('{"schema":1,"schema":2}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_json(malformed)
            output = root / "summary.json"
            completed = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/analyze_phases.py"),
                                        str(ROOT / "assets/synthetic_phase_profile.json"), "--output", str(output)],
                                       cwd=root, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(load_json(output)["runs"][0]["count"], 6)

    def test_json_float_overflow_rejected_even_in_metadata(self):
        with tempfile.TemporaryDirectory(prefix="profiler-test-", dir=ROOT) as directory:
            path = Path(directory) / "overflow.json"
            path.write_text('{"metadata":{"arbitrary":1e400}}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nonfinite JSON number"):
                load_json(path)

    def test_cli_preserves_input_and_existing_summary(self):
        with tempfile.TemporaryDirectory(prefix="profiler-test-", dir=ROOT) as directory:
            root = Path(directory)
            source = root / "trace.json"
            source.write_bytes((ROOT / "assets/synthetic_phase_profile.json").read_bytes())
            report = root / "existing.json"
            report.write_text("original report", encoding="utf-8")
            for output in (source, report):
                before = output.read_bytes()
                completed = subprocess.run([sys.executable, "-I", "-B", str(ROOT / "scripts/analyze_phases.py"),
                                            str(source), "--output", str(output)], cwd=root, capture_output=True, text=True)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(output.read_bytes(), before)

    def test_isolated_collector_and_verifier_and_sibling_preflight(self):
        with tempfile.TemporaryDirectory(prefix="profiler-test-", dir=ROOT) as directory:
            root = Path(directory)
            trace_path = root / "demo.json"
            sibling = root / "demo-outputs-B2.json"
            sibling.write_text("original sibling", encoding="utf-8")
            command = [sys.executable, "-I", "-B", str(ROOT / "scripts/collector_template.py"),
                       "--count", "4", "--vector-size", "16", "--output", str(trace_path)]
            rejected = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertEqual(sibling.read_text(encoding="utf-8"), "original sibling")
            self.assertFalse(trace_path.exists())
            sibling.unlink()
            collected = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertEqual(collected.returncode, 0, collected.stderr)
            reference = root / "demo-outputs-A1.json"
            candidate = root / "demo-outputs-B1.json"
            numeric_report = root / "numeric.json"
            verify = [sys.executable, "-I", "-B", str(ROOT / "scripts/verify_outputs.py"),
                      str(reference), str(candidate), "--atol", "0", "--rtol", "0", "--output"]
            checked = subprocess.run([*verify, str(numeric_report)], cwd=root, capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)
            self.assertEqual(load_json(numeric_report)["status"], "pass")
            for output in (reference, numeric_report):
                before = output.read_bytes()
                rejected = subprocess.run([*verify, str(output)], cwd=root, capture_output=True, text=True)
                self.assertEqual(rejected.returncode, 2)
                self.assertEqual(output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
