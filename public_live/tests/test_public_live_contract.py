"""Synthetic stdlib-only checks for the explicit public-live file contract.

Only public_live_contract.py is imported by these tests. No engineering module,
real asset, native library, board, build tool or network endpoint is loaded.
The product's pinned-asset table may be mocked in an individual synthetic test;
the product API itself is never modified to allow a caller-supplied pin override.
"""
from pathlib import Path
import hashlib
import importlib.util
import io
import json
import multiprocessing
import pickle
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile, ZipInfo
from types import ModuleType
from importlib.machinery import ModuleSpec


WORK = Path(__file__).resolve().parents[1]
CONTRACT_SOURCE = WORK / "runtime/public_live_contract.py"


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def synthetic_arm_elf(*, elf_type=3, machine=40, flags=0x05000400):
    """Minimal ELF32 LE ARM header for static-header checks, never loaded."""
    ident = b"\x7fELF\x01\x01\x01" + b"\0" * 9
    return struct.pack("<16sHHIIIIIHHHHHH", ident, elf_type, machine, 1,
                       0, 0, 0, flags, 52, 0, 0, 0, 0, 0)


def spawn_dict_echo(connection, value):
    """Child only round-trips builtin data; no contract import or execution."""
    try:
        restored = pickle.loads(pickle.dumps(value))
        connection.send((type(restored).__name__, restored))
    finally:
        connection.close()


def import_contract_only():
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("tested_public_live_contract", CONTRACT_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("public live contract source is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicLiveContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.product_source_sha_at_import = digest(CONTRACT_SOURCE.read_bytes())
        cls.module = import_contract_only()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="public-live-contract-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "release"
        self.root.mkdir()
        self.assets = {}
        self.blobs = {}
        for role in self.module.FIXED_ASSET_SHA256:
            if role == "bit":
                name, blob = "assets/design.bit", b"synthetic bit payload"
            elif role == "hwh":
                name, blob = "assets/design.hwh", b"<SYSTEM SYNTHETIC='true'/>"
            elif role == "native_source":
                name, blob = "native_source/statistics.c", b"/* synthetic C; never compiled */\n"
            elif role.endswith("_binary"):
                basename = "_v3b25_statistics_dot" if role == "native_binary" else role
                name = "native-build/" + basename + ".so"
                blob = synthetic_arm_elf() + role.encode("ascii") + b"\0"
                if role == "native_binary":
                    blob += b"PyInit__v3b25_statistics_dot\0"
            else:
                self.fail("fixture needs an explicit synthetic asset for " + role)
            self.assets[role] = name
            self.blobs[name] = blob
        self.assets["arm_sos"] = "assets/arm_sos.json"
        self.blobs[self.assets["arm_sos"]] = json.dumps({
            "native_sos_hex": [[float(value).hex() for value in (1, 0, 0, 1, 0, 0)]]
        }).encode("utf-8")
        self.blobs["runtime/entry.py"] = b"VALUE = 17  # data fixture only; never imported\n"
        for name, blob in self.blobs.items():
            self.put(name, blob)
        self.synthetic_pins = {
            role: digest(self.blobs[name]) for role, name in self.assets.items()
            if role in self.module.FIXED_ASSET_SHA256
        }
        self.manifest = {
            "schema": self.module.SCHEMA,
            "files": [{"path": name, "bytes": len(blob), "sha256": digest(blob)}
                      for name, blob in sorted(self.blobs.items())],
            "assets": dict(self.assets),
            "mutable_outputs": {"files": [], "directories": []},
        }
        self.seal()

    def put(self, name, blob):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
        return path

    def seal(self):
        blob = (json.dumps(self.manifest, indent=2) + "\n").encode("utf-8")
        (self.root / self.module.MANIFEST).write_bytes(blob)
        self.manifest_sha = digest(blob)
        return self.manifest_sha

    def refresh_member(self, name):
        blob = (self.root / name).read_bytes()
        for row in self.manifest["files"]:
            if row["path"] == name:
                row.update(bytes=len(blob), sha256=digest(blob))
                return
        self.fail("test fixture tried to refresh an unlisted source")

    def contract(self, expected=None):
        return self.module.make_contract(
            self.root, self.manifest_sha if expected is None else expected)

    def verify(self, *, pins=None, contract=None):
        # Test-only mock; no override argument is added to the product API.
        with patch.object(self.module, "FIXED_ASSET_SHA256",
                          self.synthetic_pins if pins is None else pins):
            return self.module.verify_release(self.contract() if contract is None else contract)

    def output_file(self, name="results/result.json"):
        self.manifest["mutable_outputs"]["files"] = [name]
        self.seal()
        return name

    def result_zip(self, members, name="results/result.zip"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with ZipFile(path, "w") as archive:
                for member_name, blob in members:
                    archive.writestr(member_name, blob)
        return path

    def notebook(self):
        return {"nbformat": 4, "nbformat_minor": 5,
                "metadata": {"kernelspec": {"name": "python3", "language": "python", "display_name": "UI label"},
                             "language_info": {"name": "python", "version": "host-only"}},
                "cells": [
                    {"cell_type": "markdown", "source": ["# 测试标题\n", "exact text\n"],
                     "metadata": {"tags": ["intro"]}, "attachments": {"tiny.png": {"image/png": "AA=="}}},
                    {"cell_type": "code", "source": ["value = 1\n", "print(value)\n"],
                     "metadata": {"tags": ["run", "checked"], "trusted": False},
                     "outputs": [], "execution_count": None, "id": "initial-id"},
                    {"cell_type": "raw", "source": " raw text\n", "metadata": {}}]}

    def expected_notebook_identity(self, book):
        # Independent canonical object specified by the supplied identity.md;
        # never ask the implementation under test to generate fixture hashes.
        cells = [{"cell_type": cell["cell_type"],
                  "source": "".join(cell["source"]) if isinstance(cell["source"], list) else cell["source"],
                  "tags": cell.get("metadata", {}).get("tags", []),
                  "attachments": cell.get("attachments", {})} for cell in book["cells"]]
        identity = {"policy": "notebook-source-v1", "nbformat": 4,
                    "nbformat_minor": book["nbformat_minor"],
                    "kernel_name": book["metadata"]["kernelspec"]["name"],
                    "kernel_language": book["metadata"]["kernelspec"]["language"],
                    "language_name": book["metadata"]["language_info"]["name"], "cells": cells}
        return json.dumps(identity, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")

    def write_notebook(self, book, name="PublicLive.ipynb"):
        return self.put(name, (json.dumps(book, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def register_notebook(self, book=None, *, kind="notebook-source-v1"):
        book = self.notebook() if book is None else book
        path = self.write_notebook(book)
        data = path.read_bytes() if kind == "bytes" else self.expected_notebook_identity(book)
        row = {"path": "PublicLive.ipynb", "bytes": len(data), "sha256": digest(data)}
        if kind != "bytes":
            row["identity"] = kind
        self.manifest["files"].append(row)
        self.seal()
        return book

    def allow_checkpoint(self):
        book = self.register_notebook()
        self.manifest["notebook_checkpoint_copies"] = {
            ".ipynb_checkpoints/PublicLive-checkpoint.ipynb": "PublicLive.ipynb"}
        self.seal()
        return book

    def unrelated_cached_module(self, name, *, location=None, spec_location=None):
        old = Path(self.temporary.name) / ("old-" + name.replace(".", "-") + ".py")
        old.write_bytes(b"# synthetic cached module; never executed\n")
        module = ModuleType(name)
        module.__file__ = str(old if location is None else location)
        module.__spec__ = ModuleSpec(name, loader=None,
                                     origin=str(old if spec_location is None else spec_location))
        return module

    def test_product_keeps_original_asset_pins(self):
        pins = self.module.FIXED_ASSET_SHA256
        expected = {
            "bit": "0a91f3f16740edb5fb7f947945fa5c965b83efd298df9e00250c9934087a8f7c",
            "hwh": "b652e060e8954e480ca03be4f90c239a83b0b131e6503fccf504d64d000a626a",
            "native_binary": "4dc17698315564f4d2ac50b5e3d1607fecfe12f2520dafa9f4aaa40ff4e50c78",
            "native_source": "a3758e091fbb66ab5fd9817c847dee44a294c34a07bd56ac04e2a42621ee0b59",
            "main_native_binary": "61ccbec43c8f7b610ea2ec08d6b4ac139db2000b006a91c4e0ae6c9cfd128840",
            "native_readback_binary": "48667f6655746ebe490a8bb1c5baaa9c61e148031ebac451e8f3fc9cc49fde85",
            "sample_entry_binary": "d3d51ac5a9a6f9f83703f8e32fb693cbfa1bbf4e8f2f64f0bdd59b7c1f963dac",
            "schedule_binary": "f0bacc84eddeaeb7c520d90c3ec74d693a918ecaa064899420267f92bd4a5d88",
        }
        self.assertEqual(pins, expected)
        self.assertEqual(sum(role.endswith("_binary") for role in pins), 5)

    def test_valid_complete_synthetic_release(self):
        context = self.verify()
        self.assertEqual(set(context["assets"]), set(self.assets))
        self.assertEqual(context["manifest_sha256"], self.manifest_sha)
        self.assertIs(context["historical_numerical_qualification"], False)
        self.assertIs(context["hardware_accessed"], False)

    def test_contract_is_only_builtin_pickleable_data(self):
        contract = self.contract()
        self.assertEqual(set(contract), {"schema", "root", "expected_manifest_sha256"})
        self.assertTrue(all(isinstance(value, str) for value in contract.values()))
        self.assertEqual(pickle.loads(pickle.dumps(contract)), contract)

    def test_contract_can_cross_real_spawn_as_data(self):
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        child = context.Process(target=spawn_dict_echo, args=(sender, self.contract()))
        child.start()
        sender.close()
        try:
            self.assertTrue(receiver.poll(15), "pure-data child did not return")
            typename, value = receiver.recv()
            self.assertEqual(typename, "dict")
            self.assertEqual(value, self.contract())
            child.join(10)
            self.assertEqual(child.exitcode, 0)
        finally:
            receiver.close()
            if child.is_alive():
                child.terminate()
                child.join(5)
            child.close()

    def test_explicit_expected_hash_is_required(self):
        for value in (None, "", "0" * 63, "A" * 64, 42):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.module.make_contract(self.root, value)
        contract = self.contract()
        del contract["expected_manifest_sha256"]
        with self.assertRaises(ValueError):
            self.verify(contract=contract)

    def test_contract_rejects_extra_field_or_relative_root(self):
        for change in ({"allow_unpinned": True}, {"root": "relative/root"}):
            with self.subTest(change=change):
                contract = dict(self.contract(), **change)
                with self.assertRaises(ValueError):
                    self.verify(contract=contract)

    def test_manifest_digest_mismatch(self):
        with self.assertRaisesRegex(ValueError, "manifest SHA256"):
            self.verify(contract=self.contract(expected="0" * 64))

    def test_duplicate_json_key_rejected(self):
        blob = ('{"schema":"' + self.module.SCHEMA + '","schema":"' +
                self.module.SCHEMA + '","files":[]}').encode()
        (self.root / self.module.MANIFEST).write_bytes(blob)
        self.manifest_sha = digest(blob)
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            self.verify()

    def test_manifest_rejects_path_traversal_and_alias_spellings(self):
        original = self.manifest["files"][0]["path"]
        for name in ("../escape.py", "/absolute.py", "C:/escape.py", "runtime\\entry.py",
                     "runtime//entry.py", "runtime/./entry.py", "runtime/../entry.py"):
            with self.subTest(name=name):
                self.manifest["files"][0]["path"] = name
                self.seal()
                with self.assertRaises(ValueError):
                    self.verify()
        self.manifest["files"][0]["path"] = original

    def test_manifest_rejects_duplicate_and_case_colliding_paths(self):
        row = dict(self.manifest["files"][0])
        for name in (row["path"], row["path"].upper()):
            with self.subTest(name=name):
                self.manifest["files"].append(dict(row, path=name))
                self.seal()
                with self.assertRaises(ValueError):
                    self.verify()
                self.manifest["files"].pop()

    def test_changed_or_missing_listed_source_rejected(self):
        name = "runtime/entry.py"
        self.put(name, b"CHANGED = True\n")
        with self.assertRaisesRegex(ValueError, "member identity"):
            self.verify()
        (self.root / name).unlink()
        with self.assertRaisesRegex(ValueError, "complete file set"):
            self.verify()

    def test_unlisted_source_cache_or_native_asset_rejected(self):
        for name in ("runtime/extra.py", "runtime/__pycache__/extra.pyc", "native-build/extra.so"):
            with self.subTest(name=name):
                self.put(name, b"synthetic unlisted bytes")
                with self.assertRaisesRegex(ValueError, "complete file set"):
                    self.verify()
                (self.root / name).unlink()

    def test_missing_required_asset_role_rejected(self):
        for role in self.assets:
            with self.subTest(role=role):
                value = self.manifest["assets"].pop(role)
                self.seal()
                with self.assertRaisesRegex(ValueError, "required asset roles"):
                    self.verify()
                self.manifest["assets"][role] = value

    def test_unlisted_or_reused_asset_path_rejected(self):
        original = self.manifest["assets"]["bit"]
        for name in ("assets/unlisted.bit", self.assets["hwh"]):
            with self.subTest(name=name):
                self.manifest["assets"]["bit"] = name
                self.seal()
                with self.assertRaises(ValueError):
                    self.verify()
        self.manifest["assets"]["bit"] = original

    def test_resealed_changed_pinned_asset_still_rejected(self):
        for role in self.synthetic_pins:
            with self.subTest(role=role):
                name = self.assets[role]
                self.put(name, self.blobs[name] + b"tamper")
                self.refresh_member(name)
                self.seal()
                with self.assertRaisesRegex(ValueError, "fixed original asset"):
                    self.verify()
                self.put(name, self.blobs[name])
                self.refresh_member(name)

    def test_native_elf_wrong_type_machine_or_encoding_rejected(self):
        for role in self.synthetic_pins:
            if not role.endswith("_binary"):
                continue
            for kind in ("type", "machine", "encoding", "truncated"):
                with self.subTest(role=role, kind=kind):
                    blob = synthetic_arm_elf(elf_type=2 if kind == "type" else 3,
                                             machine=62 if kind == "machine" else 40)
                    if kind == "encoding":
                        blob = blob[:5] + b"\x02" + blob[6:]
                    if kind == "truncated":
                        blob = blob[:25]
                    if role == "native_binary" and kind != "truncated":
                        blob += b"PyInit__v3b25_statistics_dot\0"
                    name = self.assets[role]
                    self.put(name, blob)
                    self.refresh_member(name)
                    self.seal()
                    pins = dict(self.synthetic_pins, **{role: digest(blob)})
                    with self.assertRaisesRegex(ValueError, "ELF32 ARM"):
                        self.verify(pins=pins)
                    self.put(name, self.blobs[name])
                    self.refresh_member(name)

    def test_statistics_init_symbol_required_after_test_pin_matches(self):
        role = "native_binary"
        blob = synthetic_arm_elf() + b"PyInit__other_module\0"
        self.put(self.assets[role], blob)
        self.refresh_member(self.assets[role])
        self.seal()
        with self.assertRaisesRegex(ValueError, "preserved Python ABI"):
            self.verify(pins=dict(self.synthetic_pins, **{role: digest(blob)}))

    def test_native_context_and_sos_remain_data_without_loading_library(self):
        before = set(sys.modules)
        with patch.object(self.module, "FIXED_ASSET_SHA256", self.synthetic_pins):
            native = self.module.native_context(self.contract())
            sections = self.module.read_sections(self.contract())
        self.assertEqual(sections, ((1.0, 0.0, 0.0, 1.0, 0.0, 0.0),))
        self.assertEqual(native["binary"]["sha256"], self.synthetic_pins["native_binary"])
        self.assertIs(native["historical_numerical_qualification"], False)
        self.assertIsNone(native["preparation_sha256"])
        self.assertNotIn("_v3b25_statistics_dot", set(sys.modules) - before)

    def test_sos_rejects_wrong_shape_nonfinite_and_duplicate_keys(self):
        name = self.assets["arm_sos"]
        examples = [b'{"native_sos_hex":[["0x1p+0"]]}',
                    json.dumps({"native_sos_hex": [["inf"] * 6]}).encode(),
                    b'{"native_sos_hex":[],"native_sos_hex":[]}']
        for blob in examples:
            with self.subTest(blob=blob):
                self.put(name, blob)
                self.refresh_member(name)
                self.seal()
                with patch.object(self.module, "FIXED_ASSET_SHA256", self.synthetic_pins):
                    with self.assertRaises(ValueError):
                        self.module.read_sections(self.contract())

    def test_exact_mutable_file_and_directory_data_are_allowed(self):
        self.manifest["mutable_outputs"] = {
            "files": ["result.json"], "directories": ["results"]}
        self.seal()
        self.put("result.json", b'{"complete":true}')
        self.put("results/phase/timing.csv", b"sequence,elapsed_ns\n0,4\n")
        self.verify()

    def test_output_outside_whitelist_rejected(self):
        self.output_file("result.json")
        self.put("other-result.json", b"{}")
        with self.assertRaisesRegex(ValueError, "complete file set"):
            self.verify()

    def test_mutable_declarations_cannot_shadow_code_assets_or_immutable_tree(self):
        for key, name in (("files", self.assets["bit"]), ("files", "public-live-manifest.json"),
                          ("files", "run.py"), ("files", "nested/X.SO"),
                          ("directories", "runtime"), ("directories", "../outside")):
            with self.subTest(key=key, name=name):
                self.manifest["mutable_outputs"] = {"files": [], "directories": []}
                self.manifest["mutable_outputs"][key] = [name]
                self.seal()
                with self.assertRaises(ValueError):
                    self.verify()

    def test_mutable_output_rejects_direct_code_and_cache(self):
        self.manifest["mutable_outputs"]["directories"] = ["results"]
        self.seal()
        for name in ("results/payload.py", "results/PAYLOAD.SO", "results/__pycache__/payload.dat"):
            with self.subTest(name=name):
                self.put(name, b"synthetic forbidden executable")
                with self.assertRaisesRegex(ValueError, "executable or hardware asset"):
                    self.verify()
                (self.root / name).unlink()

    def test_result_zip_accepts_only_exact_manifest_source_copy(self):
        self.output_file("results/result.zip")
        self.result_zip([("audit/entry.py", self.blobs["runtime/entry.py"]),
                         ("results.json", b'{"count":1}')])
        self.verify()

    def test_result_zip_rejects_unknown_or_changed_source(self):
        self.output_file("results/result.zip")
        for name, blob in (("unknown.py", b"VALUE = 99\n"),
                           ("audit/entry.py", b"VALUE = 18\n")):
            with self.subTest(name=name):
                self.result_zip([(name, blob)])
                with self.assertRaisesRegex(ValueError, "unlisted or changed source"):
                    self.verify()

    def test_result_zip_rejects_traversal_duplicate_case_and_symlink(self):
        self.output_file("results/result.zip")
        link = ZipInfo("linked.json")
        link.create_system = 3
        link.external_attr = 0o120777 << 16
        cases = [[("../escape.json", b"{}")],
                 [("result.json", b"{}"), ("RESULT.json", b"{}")],
                 [(link, b"../../outside")]]
        for members in cases:
            with self.subTest(members=[str(x[0]) for x in members]):
                self.result_zip(members)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_result_zip_rejects_even_unchanged_listed_native_binary(self):
        self.output_file("results/result.zip")
        name = self.assets["native_binary"]
        self.result_zip([(Path(name).name, self.blobs[name])])
        with self.assertRaises(ValueError):
            self.verify()

    def test_mutable_data_name_cannot_disguise_elf_binary(self):
        self.output_file("results/result.json")
        self.put("results/result.json", synthetic_arm_elf() + b"binary disguised as json")
        with self.assertRaises(ValueError):
            self.verify()

    def test_nested_result_zip_cannot_hide_unlisted_source(self):
        self.output_file("results/result.zip")
        inner = io.BytesIO()
        with ZipFile(inner, "w") as archive:
            archive.writestr("unlisted.py", b"VALUE = 99\n")
        self.result_zip([("inner.zip", inner.getvalue())])
        with self.assertRaises(ValueError):
            self.verify()

    def test_notebook_identity_exact_canonical_skill_definition(self):
        book = self.notebook()
        path = self.write_notebook(book)
        expected = self.expected_notebook_identity(book)
        self.assertEqual(self.module.identity_bytes(path, "notebook-source-v1"), expected)
        self.assertEqual(self.module.identity_bytes(path), path.read_bytes())
        self.assertEqual(self.module.identity_bytes(path, "bytes"), path.read_bytes())
        self.assertNotEqual(expected, path.read_bytes())

    def test_notebook_saved_outputs_trusted_ids_and_nonidentity_metadata_pass(self):
        book = self.register_notebook()
        book["cells"][1].update(outputs=[{"output_type": "stream", "name": "stdout", "text": ["saved output\n"]}],
                                 execution_count=37, id="new-cell-id")
        book["cells"][1]["metadata"].update(trusted=True, execution_time="ignored")
        book["metadata"]["kernelspec"]["display_name"] = "New visible kernel label"
        book["metadata"]["language_info"]["version"] = "different-host-version"
        book["metadata"]["widgets"] = {"display_only": True}
        self.write_notebook(book)
        self.verify()

    def test_notebook_source_list_and_string_are_equal_without_normalization(self):
        book = self.register_notebook()
        for cell in book["cells"]:
            if isinstance(cell["source"], list):
                cell["source"] = "".join(cell["source"])
        self.write_notebook(book)
        self.verify()
        book["cells"][1]["source"] = book["cells"][1]["source"].rstrip("\n")
        self.write_notebook(book)
        with self.assertRaises(ValueError):
            self.verify()

    def test_notebook_code_change_fails(self):
        book = self.register_notebook()
        book["cells"][1]["source"][0] = "value = 2\n"
        self.write_notebook(book)
        with self.assertRaises(ValueError):
            self.verify()

    def test_notebook_cell_order_change_fails(self):
        book = self.register_notebook()
        book["cells"][0], book["cells"][1] = book["cells"][1], book["cells"][0]
        self.write_notebook(book)
        with self.assertRaises(ValueError):
            self.verify()

    def test_notebook_tags_attachment_minor_and_cell_type_changes_fail(self):
        baseline = self.register_notebook()
        for field in ("tags", "attachments", "minor", "cell_type"):
            with self.subTest(field=field):
                book = json.loads(json.dumps(baseline))
                if field == "tags":
                    book["cells"][1]["metadata"]["tags"].reverse()
                elif field == "attachments":
                    book["cells"][0]["attachments"]["tiny.png"]["image/png"] = "AB=="
                elif field == "minor":
                    book["nbformat_minor"] = 6
                else:
                    book["cells"][0]["cell_type"] = "raw"
                self.write_notebook(book)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_notebook_kernel_and_language_identity_changes_fail(self):
        baseline = self.register_notebook()
        for branch, key in (("kernelspec", "name"), ("kernelspec", "language"), ("language_info", "name")):
            with self.subTest(branch=branch, key=key):
                book = json.loads(json.dumps(baseline))
                book["metadata"][branch][key] = "changed-identity"
                self.write_notebook(book)
                with self.assertRaises(ValueError):
                    self.verify()

    def test_notebook_bytes_default_does_not_ignore_saved_metadata(self):
        book = self.register_notebook(kind="bytes")
        book["cells"][1]["metadata"]["trusted"] = True
        self.write_notebook(book)
        with self.assertRaises(ValueError):
            self.verify()

    def test_notebook_policy_rejects_missing_identity_or_unknown_policy(self):
        book = self.notebook()
        del book["metadata"]["language_info"]["name"]
        path = self.write_notebook(book)
        with self.assertRaises(ValueError):
            self.module.identity_bytes(path, "notebook-source-v1")
        with self.assertRaises(ValueError):
            self.module.identity_bytes(path, "notebook-source-v999")

    def test_exact_checkpoint_allows_same_source_with_different_outputs(self):
        book = self.allow_checkpoint()
        book["cells"][1].update(execution_count=99, outputs=[{"output_type": "stream", "name": "stdout", "text": "checkpoint output"}])
        book["cells"][1]["metadata"]["trusted"] = True
        self.write_notebook(book, ".ipynb_checkpoints/PublicLive-checkpoint.ipynb")
        self.verify()

    def test_exact_checkpoint_rejects_changed_code(self):
        book = self.allow_checkpoint()
        book["cells"][1]["source"][0] = "value = 1234\n"
        self.write_notebook(book, ".ipynb_checkpoints/PublicLive-checkpoint.ipynb")
        with self.assertRaises(ValueError):
            self.verify()

    def test_checkpoint_directory_does_not_ignore_extra_code_or_other_notebooks(self):
        book = self.allow_checkpoint()
        self.write_notebook(book, ".ipynb_checkpoints/PublicLive-checkpoint.ipynb")
        extras = [(".ipynb_checkpoints/hidden.py", b"VALUE = 88\n"),
                  (".ipynb_checkpoints/Other-checkpoint.ipynb", json.dumps(book).encode())]
        for name, blob in extras:
            with self.subTest(name=name):
                self.put(name, blob)
                with self.assertRaises(ValueError):
                    self.verify()
                (self.root / name).unlink()

    def test_checkpoint_source_must_use_notebook_policy(self):
        self.register_notebook(kind="bytes")
        self.manifest["notebook_checkpoint_copies"] = {
            ".ipynb_checkpoints/PublicLive-checkpoint.ipynb": "PublicLive.ipynb"}
        self.seal()
        with self.assertRaises(ValueError):
            self.verify()

    def test_only_exact_checkpoint_mapping_is_admitted(self):
        self.register_notebook()
        self.manifest["notebook_checkpoint_copies"] = {
            ".ipynb_checkpoints/Arbitrary-checkpoint.ipynb": "PublicLive.ipynb"}
        self.seal()
        with self.assertRaises(ValueError):
            self.verify()

    def test_mutable_outputs_cannot_ignore_whole_checkpoint_directory(self):
        self.allow_checkpoint()
        self.manifest["mutable_outputs"]["directories"] = [".ipynb_checkpoints"]
        self.seal()
        with self.assertRaises(ValueError):
            self.verify()

    def test_checkpoint_symlink_is_rejected(self):
        book = self.allow_checkpoint()
        source = self.root / "PublicLive.ipynb"
        link = self.root / ".ipynb_checkpoints/PublicLive-checkpoint.ipynb"
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(source)
        except OSError as exc:
            # Windows may deny symlink creation. The fallback checks the exact
            # filesystem predicate used by the guard and is recorded explicitly.
            self.write_notebook(book, link.relative_to(self.root).as_posix())
            original = Path.is_symlink
            self.__class__.symlink_test_mode = "mocked_exact_path_predicate; OS symlink creation denied"
            with patch.object(Path, "is_symlink", lambda path: path == link or original(path)):
                with self.assertRaises(ValueError):
                    self.verify()
        else:
            self.__class__.symlink_test_mode = "real_temporary_filesystem_symlink"
            with self.assertRaises(ValueError):
                self.verify()

    def test_cached_old_core_rejected_by_verify_and_activation(self):
        old_module = self.unrelated_cached_module("heart_v2")
        context = {"runtime_root": str(self.root / "runtime")}
        with patch.dict(sys.modules, {"heart_v2": old_module}):
            with self.assertRaises(RuntimeError):
                self.verify()
            with patch.object(self.module, "verify_release", return_value=context):
                with self.assertRaises(RuntimeError):
                    self.module.activate_runtime(self.contract())

    def test_cached_old_runtime_top_module_rejected_without_executing_it(self):
        name = "runtime/small_heart_worker.py"
        blob = b"# synthetic immutable module; never executed\n"
        self.put(name, blob)
        self.manifest["files"].append({"path": name, "bytes": len(blob), "sha256": digest(blob)})
        self.seal()
        old_module = self.unrelated_cached_module("small_heart_worker")
        with patch.dict(sys.modules, {"small_heart_worker": old_module}):
            with self.assertRaises(RuntimeError):
                self.verify()

    def test_cached_file_and_spec_origins_must_agree(self):
        module = self.unrelated_cached_module("entry", location=self.root / "runtime/entry.py")
        with patch.dict(sys.modules, {"entry": module}):
            with self.assertRaisesRegex(RuntimeError, "file/spec origins"):
                self.verify()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(PublicLiveContractTests)
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    before = getattr(PublicLiveContractTests, "product_source_sha_at_import", None)
    after = digest(CONTRACT_SOURCE.read_bytes())
    report = {
        "schema": "independent_public_live_contract_synthetic_tests_v1",
        "tests_run": outcome.testsRun,
        "failures": [str(test) for test, _ in outcome.failures],
        "errors": [str(test) for test, _ in outcome.errors],
        "skipped": [{"test": str(test), "reason": reason} for test, reason in outcome.skipped],
        "passed": outcome.wasSuccessful() and before == after,
        "contract_sha256_at_import": before,
        "contract_sha256_after_tests": after,
        "contract_source_changed_during_tests": before != after,
        "only_contract_product_module_imported": True,
        "asset_pins_mocked_only_for_synthetic_fixture": True,
        "real_spawn_dict_roundtrip_tested": True,
        "real_native_library_loaded": False,
        "engineering_modules_imported_or_executed": False,
        "compiled": False,
        "hardware_accessed": False,
        "network_accessed": False,
        "candidate_or_original_engineering_modified": False,
        "checkpoint_symlink_test_mode": getattr(PublicLiveContractTests, "symlink_test_mode", None),
    }
    # Keep direct invocation read-only: the JSON report is emitted on stdout.
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)
