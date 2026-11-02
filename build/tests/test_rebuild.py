"""No hardware/tool invocation: verify source packaging and failure boundaries."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

BUILD = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_rebuild", BUILD / "rebuild.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class RebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def clone_contract(self):
        target = self.root / "build"
        shutil.copytree(BUILD / "inputs", target / "inputs")
        shutil.copytree(BUILD / "scripts", target / "scripts")
        return target

    def test_real_source_archive_and_script_hashes(self):
        index, payload = module.checked_inputs(BUILD)
        self.assertEqual(len(payload), 109)
        self.assertEqual(len(index["external_files"]), 27)
        self.assertTrue(all(p == p.lower() and p.isascii() and " " not in p for p in payload))
        self.assertFalse(any(p.startswith(("ip_repo/color_convert/", "ip_repo/pixel_unpack/")) for p in payload))
        self.assertIn("hls_sources/color_convert/color_convert.cpp", payload)
        self.assertIn("ip_repo/rgb2dvi_v1_2/src/rgb2dvi_clocks.xdc", payload)

    def test_archive_tampering_rejected(self):
        build = self.clone_contract()
        archive = build / "inputs/physical-inputs.zip"
        archive.write_bytes(archive.read_bytes() + b"tampered")
        with self.assertRaisesRegex(ValueError, "archive hash mismatch"):
            module.checked_inputs(build)

    def test_script_tampering_rejected(self):
        build = self.clone_contract()
        (build / "scripts/main-joint-route.tcl").write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "script hash mismatch"):
            module.checked_inputs(build)

    def test_unpinned_external_url_rejected(self):
        build = self.clone_contract()
        path = build / "inputs/physical-inputs.json"
        index = json.loads(path.read_bytes())
        index["external_files"][0]["url"] = "https://raw.githubusercontent.com/xupsh/pynq-supported-board-file/master/pynq-z2/A.0/board.xml"
        path.write_text(json.dumps(index), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "not pinned"):
            module.checked_inputs(build)

    def test_external_overwrite_rejected(self):
        build = self.clone_contract()
        path = build / "inputs/physical-inputs.json"
        index = json.loads(path.read_bytes())
        index["external_files"][0]["path"] = next(iter(index["members"]))
        path.write_text(json.dumps(index), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            module.checked_inputs(build)

    def test_traversal_and_ambiguous_paths_rejected(self):
        for name in ("../bad", "/bad", "C:/bad", "a\\bad", "a//bad", "a/./bad", ""):
            with self.subTest(name=name), self.assertRaises(ValueError):
                module.safe_relative(name)

    def test_external_hash_checked_before_staging(self):
        row = {"path": "upstream/source.v", "sha256": module.digest(b"expected"), "bytes": 8}
        source = self.root / row["path"]
        source.parent.mkdir(parents=True)
        source.write_bytes(b"wrong")
        with self.assertRaisesRegex(ValueError, "external input hash mismatch"):
            module.read_external(row, self.root)

    def test_check_only_does_not_fetch_or_start_tool(self):
        with patch.object(module, "read_external", side_effect=AssertionError("network accessed")), patch.object(module, "tool", side_effect=AssertionError("tool started")):
            self.assertEqual(module.main(["--check-only"]), 0)

    def test_existing_output_preserved(self):
        output = self.root / "existing"
        output.mkdir()
        marker = output / "result.json"
        marker.write_text("preserve", encoding="utf-8")
        with patch.object(module, "tool", side_effect=AssertionError("tool started")), self.assertRaises(SystemExit):
            module.main(["--output", str(output), "--execute"])
        self.assertEqual(marker.read_text(), "preserve")

    def hls_zip(self, core="color_convert", evil=False):
        archive = self.root / "hls.zip"
        xml = ('<component xmlns="http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009">'
               '<vendor>xilinx.com</vendor><library>hls</library><name>' + core + '</name><version>1.0</version></component>')
        with ZipFile(archive, "w") as z:
            z.writestr("component.xml", xml)
            z.writestr("../outside" if evil else "hdl/example.v", "module example; endmodule")
        return archive

    def test_generated_core_identity_checked(self):
        dest = self.root / "output"
        with self.assertRaisesRegex(ValueError, "identity"):
            module.install_hls_archive(self.hls_zip("wrong"), dest, "color_convert")
        self.assertFalse(dest.exists())

    def test_generated_archive_traversal_rejected_before_write(self):
        dest = self.root / "output"
        with self.assertRaises(ValueError):
            module.install_hls_archive(self.hls_zip(evil=True), dest, "color_convert")
        self.assertFalse(dest.exists())

    def test_generated_core_extracts_after_validation(self):
        dest = self.root / "output"
        report = module.install_hls_archive(self.hls_zip(), dest, "color_convert")
        self.assertEqual(report["vlnv"], "xilinx.com:hls:color_convert:1.0")
        self.assertTrue((dest / "hdl/example.v").is_file())

    def test_build_failure_keeps_result_and_does_not_claim_success(self):
        dest = self.root / "failed"
        with patch.object(module, "tool", side_effect=RuntimeError("tool unavailable")), self.assertRaisesRegex(RuntimeError, "unavailable"):
            module.main(["--output", str(dest), "--execute"])
        report = json.loads((dest / "build-result.json").read_bytes())
        self.assertFalse(report["clean_build_completed"])
        self.assertFalse(report["hardware_accessed"])
        self.assertEqual(report["error"]["message"], "tool unavailable")

    def test_stage_order_preserves_base_route_and_uses_postroute_for_bit(self):
        session = self.root / "fresh"
        stages = module.vivado_stages(session, True)
        self.assertEqual([row[0] for row in stages], ["prepare", "route", "postroute", "bitstream"])
        self.assertEqual(stages[2][2], [str(session / "postroute"), str(session / "routed.dcp")])
        self.assertEqual(stages[3][2], [str(session / "postroute/routed.dcp"), str(session)])
        self.assertEqual([row[0] for row in module.vivado_stages(session, False)], ["prepare"])

    def test_postroute_script_pin_and_original_strict_gate(self):
        index, _ = module.checked_inputs()
        self.assertIn("physical-postroute.tcl", index["scripts"])
        gate = (module.HERE / "scripts/write-joint-bitstream.tcl").read_text(encoding="utf-8")
        self.assertIn("$wns < 0 || $whs < 0 || $axi != 10.0 || $pixel != 10.0 || $serial != 2.0", gate)
        self.assertIn("$errors != 0 || $critical != 0", gate)


if __name__ == "__main__":
    unittest.main()
