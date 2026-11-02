"""Preparation failures must not create an apparently usable deployment."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_delivery import prepare, validated_records


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "published"
        self.root.mkdir()
        self.output = self.base / "deployment"
        self.payload = b"original source\r\n"
        path = self.root / "board_runtime/native_source/sample.txt"
        path.parent.mkdir(parents=True)
        path.write_bytes(self.payload)
        self.row = {"group": "runtime", "published": "board_runtime/native_source/sample.txt",
                    "deployed": "board_runtime/Native Source/Sample.txt", "bytes": len(self.payload),
                    "sha256": hashlib.sha256(self.payload).hexdigest()}
        self.rows = [self.row]
        self.save()

    def save(self):
        (self.root / "deployment_map.json").write_text(json.dumps({
            "schema": "verified_deployment_map_v1", "files": self.rows}), encoding="utf-8")

    def rejects_before_output(self, exception=ValueError):
        self.save()
        with self.assertRaises(exception):
            prepare(self.root, "runtime", self.output)
        self.assertFalse(self.output.exists())

    def test_exact_bytes_and_legacy_name_restored(self):
        result = prepare(self.root, "runtime", self.output)
        self.assertTrue(result["prepared"])
        self.assertFalse(result["hardware_accessed"])
        self.assertEqual((self.output / self.row["deployed"]).read_bytes(), self.payload)

    def test_existing_output_is_not_overwritten(self):
        self.output.mkdir()
        sentinel = self.output / "keep.txt"
        sentinel.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            prepare(self.root, "runtime", self.output)
        self.assertEqual(sentinel.read_bytes(), b"keep")

    def test_corrupt_source_rejected_before_writing(self):
        (self.root / self.row["published"]).write_bytes(b"changed")
        self.rejects_before_output()

    def test_missing_source_rejected_before_writing(self):
        self.row["published"] = "board_runtime/missing.txt"
        self.rejects_before_output(FileNotFoundError)

    def test_parent_escape_source(self):
        self.row["published"] = "board_runtime/../outside.txt"
        self.rejects_before_output()

    def test_absolute_target(self):
        self.row["deployed"] = "/tmp/escape"
        self.rejects_before_output()

    def test_parent_escape_target(self):
        self.row["deployed"] = "board_runtime/../../escape"
        self.rejects_before_output()

    def test_wrong_group_target(self):
        self.row["deployed"] = "skill/skills/other.txt"
        self.rejects_before_output()

    def test_duplicate_case_target(self):
        other = dict(self.row, published="board_runtime/second.txt", deployed=self.row["deployed"].lower())
        (self.root / other["published"]).write_bytes(self.payload)
        self.rows.append(other)
        self.rejects_before_output()

    def test_duplicate_source(self):
        self.rows.append(dict(self.row, deployed="board_runtime/second.txt"))
        self.rejects_before_output()

    def test_noncompliant_published_name(self):
        self.row["published"] = "board_runtime/Upper Name.txt"
        self.rejects_before_output()

    def test_output_inside_checkout(self):
        with self.assertRaises(ValueError):
            prepare(self.root, "runtime", self.root / "new")
        self.assertFalse((self.root / "new").exists())

    def test_check_does_not_create_output(self):
        self.assertEqual(len(validated_records(self.root, "runtime")), 1)
        self.assertFalse(self.output.exists())

    def test_empty_group(self):
        with self.assertRaises(ValueError):
            validated_records(self.root, "skills")

    def test_file_directory_collision(self):
        other = dict(self.row, published="board_runtime/second.txt", deployed=self.row["deployed"] + "/child")
        (self.root / other["published"]).write_bytes(self.payload)
        self.rows.append(other)
        self.rejects_before_output()


if __name__ == "__main__":
    unittest.main()
