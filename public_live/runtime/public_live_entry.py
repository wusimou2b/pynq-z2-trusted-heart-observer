"""Public four-stage entry. Importing this module does not access hardware."""
import importlib
import json
import os
from pathlib import Path
import sys
import uuid

sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE']='1'
from public_live_contract import make_contract, verify_release


class PublicLiveSession:
    """Bind each one-attempt stage to one checked release and one kernel session."""
    def __init__(self, root, expected_manifest_sha256):
        self.contract = make_contract(root, expected_manifest_sha256)
        context = verify_release(self.contract)
        self.runtime = Path(context["runtime_root"])
        if Path(__file__).resolve().parent != self.runtime:
            raise ValueError('public entry module comes from another release; use a fresh kernel')
        self.manifest_sha256 = context["manifest_sha256"]
        self.session_id = uuid.uuid4().hex
        self._prepared = False

    def check(self):
        context = verify_release(self.contract)
        from public_live_dependencies import dependency_report
        dependencies=dependency_report()
        dependency_complete=bool(dependencies.get('modules_available') is True
            and dependencies.get('target_abi_matches') is True
            and (dependencies.get('versions') or {}).get('numpy')=='1.21.5')
        return dict(schema="trusted_heart_public_live_identity_v1",
                    release_manifest_sha256=context["manifest_sha256"],
                    asset_identity_verified=True, hardware_accessed=False,
                    historical_numerical_qualification=False,
                    new_release_board_verified=False,dependency_complete=dependency_complete,
                    dependencies=dependencies)

    def _read_stage(self, name):
        path = self.runtime / ("public-" + name + ".json")
        if not path.is_file():
            raise ValueError("matching public " + name + " stage required")
        result = json.loads(path.read_text(encoding="utf-8"))
        if (result.get("schema") != "trusted_heart_public_stage_v1"
                or result.get("release_manifest_sha256") != self.manifest_sha256
                or result.get("session_id") != self.session_id
                or result.get("error") is not None):
            raise ValueError("public stage identity differs: " + name)
        return result.get("result") or {}

    def _require_short(self):
        stage = self._read_stage("short")
        if stage.get("passed") is not True or stage.get("hardware_accessed") is not False:
            raise ValueError("passed hardware-free public short required")

    def _require_preview(self):
        self._require_short()
        if self._read_stage("preview20").get("ownership_qualification_passed") is not True:
            raise ValueError("public video ownership and cleanup qualification required")

    def _stage(self, name, method):
        verify_release(self.contract)
        attempt = self.runtime / ("public-" + name + "-attempt.json")
        with attempt.open("x", encoding="utf-8") as sink:
            json.dump(dict(schema="trusted_heart_public_attempt_v1", stage=name,
                           session_id=self.session_id,
                           release_manifest_sha256=self.manifest_sha256,
                           automatic_retry=False), sink, indent=2)
        result = None
        failure = None
        try:
            backend = importlib.import_module("public_live_runtime")
            result = getattr(backend, method)(self.contract)
            verify_release(self.contract)
        except BaseException as exc:
            failure = exc
        receipt = dict(schema="trusted_heart_public_stage_v1", stage=name,
                       session_id=self.session_id,
                       release_manifest_sha256=self.manifest_sha256,
                       result=result,
                       error=None if failure is None else dict(type=type(failure).__name__, message=str(failure)),
                       automatic_retry=False,
                       historical_numerical_qualification=False,
                       new_release_board_verified=False)
        with (self.runtime / ("public-" + name + ".json")).open("x", encoding="utf-8") as sink:
            json.dump(receipt, sink, ensure_ascii=False, indent=2, allow_nan=False)
        if failure is not None:
            raise failure
        return receipt

    def short(self):
        from public_live_dependencies import require_dependencies
        # Refuse unsupported hosts/missing packages before creating the
        # non-repeatable attempt or importing/spawning the native backend.
        require_dependencies()
        return self._stage("short", "short")

    def preview20(self, *, hardware=False, confirmation=None):
        if hardware is not True or confirmation != "RUN-PUBLIC-VIDEO20":
            raise ValueError("explicit hardware=True and RUN-PUBLIC-VIDEO20 required")
        verify_release(self.contract)
        self._require_short()
        from public_live_dependencies import require_dependencies
        require_dependencies()
        return self._stage("preview20", "preview20")

    def prepare(self):
        verify_release(self.contract)
        self._require_preview()
        if self._prepared:
            raise RuntimeError("display already prepared; preserve the original session")
        receipt = self._stage("prepare", "prepare")
        self._prepared = (receipt["result"] or {}).get("prepared") is True
        if not self._prepared:
            raise RuntimeError("public display preparation incomplete")
        return receipt

    def run(self, *, hardware=False, confirmation=None):
        if hardware is not True or confirmation != "RUN-PUBLIC-LIVE25":
            raise ValueError("explicit hardware=True and RUN-PUBLIC-LIVE25 required")
        verify_release(self.contract)
        self._require_preview()
        if not self._prepared:
            raise ValueError("prepare display in a separate cell and wait for green readiness")
        from public_live_dependencies import require_dependencies
        require_dependencies()
        return self._stage("live", "run")
