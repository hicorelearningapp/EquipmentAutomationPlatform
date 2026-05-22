"""
test_mes_family_api.py
======================
OOP-style test suite for all 6 MES Family / Template endpoints.

Usage:
    python test_mes_family_api.py        # normal
    python test_mes_family_api.py -v     # verbose (print response body on every call)
"""

import argparse
import io
import json
import sys
import requests


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
BASE_URL = "http://151.185.41.194:8012"

SEEDED_FAMILIES = [
    "FactoryWorks",
    "FAB300",
    "PROMIS",
    "Camstar",
    "Critical Manufacturing",
    "Custom MES",
]

TEST_TEMPLATE_NAME = "TEST_AUTO_TEMPLATE_DO_NOT_USE"


# ─────────────────────────────────────────────────────────────────────────────
# TestRunner  —  tracks pass/fail, provides assert helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestRunner:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0

    # ── Core assertion ────────────────────────────────────────────────────────
    def assert_status(self, label: str, response: requests.Response, expected: int) -> bool:
        ok = response.status_code == expected
        sym = "✅" if ok else "❌"
        print(f"  {sym}  [{response.status_code} vs {expected}]  {label}")
        if not ok or self.verbose:
            try:
                body = json.dumps(response.json(), indent=2)
            except Exception:
                body = response.text
            print(f"       Response: {body[:600]}")
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok

    def assert_true(self, label: str, condition: bool, detail: str = "") -> bool:
        sym = "✅" if condition else "❌"
        print(f"  {sym}  {label}" + (f" — {detail}" if detail else ""))
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    # ── Summary ───────────────────────────────────────────────────────────────
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"  Results: {self.passed} / {total} passed  |  {self.failed} failed")
        print(f"{'='*60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# BaseTestGroup  —  shared session, helpers, runner reference
# ─────────────────────────────────────────────────────────────────────────────
class BaseTestGroup:
    def __init__(self, runner: TestRunner, session: requests.Session, base_url: str):
        self.runner = runner
        self.session = session
        self.base = base_url

    def _url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def _make_template(self, mes_family: str, template_name: str) -> dict:
        return {
            "MESFamily": mes_family,
            "TemplateName": template_name,
            "Version": "1.0",
            "Description": "Test template",
            "Events": [],
            "Alarms": [],
            "Variables": [],
            "Payloads": [],
            "Transactions": [],
            "ValidationRules": [],
            "AutoMapping": {"Enabled": True},
            "Logging": {"Enabled": True},
        }

    def _upload_template(
        self,
        mes_family: str,
        filename: str,
        payload: dict | bytes,
        content_type: str = "application/json",
    ) -> requests.Response:
        data = json.dumps(payload).encode() if isinstance(payload, dict) else payload
        files = {"file": (filename, io.BytesIO(data), content_type)}
        return self.session.post(self._url(f"AddMesTemplateInfo/{mes_family}"), files=files)

    def _update_template(
        self, mes_family: str, template: str, payload: dict
    ) -> requests.Response:
        data = json.dumps(payload).encode()
        files = {"file": (f"{template}.json", io.BytesIO(data), "application/json")}
        return self.session.put(
            self._url(f"UpdateMesTemplateInfo/{mes_family}/{template}"), files=files
        )

    def _get_families(self) -> list:
        r = self.session.get(self._url("GetMesFamilies"))
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("MESFamilies", [])

    def run(self):
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — GetMesFamilies
# ─────────────────────────────────────────────────────────────────────────────
class TestGetMesFamilies(BaseTestGroup):
    def run(self):
        print("\n── Group 1: GET /GetMesFamilies ──")
        r = self.session.get(self._url("GetMesFamilies"))
        self.runner.assert_status("returns 200", r, 200)

        families = r.json() if isinstance(r.json(), list) else r.json().get("MESFamilies", [])
        names = [f.get("Family") for f in families]

        self.runner.assert_true(
            "all 6 seeded families present",
            all(s in names for s in SEEDED_FAMILIES),
            f"found: {names}",
        )

        missing_keys = [
            key
            for entry in families
            for key in ("Family", "DefaultProtocol", "RequiresAck", "Description")
            if key not in entry
        ]
        self.runner.assert_true(
            "all family entries have required keys",
            not missing_keys,
            f"missing: {missing_keys}" if missing_keys else "",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — UpdateMesFamilies
# ─────────────────────────────────────────────────────────────────────────────
class TestUpdateMesFamilies(BaseTestGroup):
    def run(self):
        print("\n── Group 2: POST /UpdateMesFamilies ──")
        current = self._get_families()

        new_entry = {
            "FamilyID": None,
            "Family": "TestFamily_XYZ",
            "DefaultProtocol": "REST/JSON",
            "RequiresAck": False,
            "Description": "Temporary test family",
        }

        # 2a. Add new family
        r = self.session.post(self._url("UpdateMesFamilies"), json=current + [new_entry])
        ok = self.runner.assert_status("add new family → 200", r, 200)
        if ok:
            returned = r.json().get("Families", [])
            names = [f["Family"] for f in returned]
            new_id = next((f["FamilyID"] for f in returned if f["Family"] == "TestFamily_XYZ"), None)
            self.runner.assert_true("TestFamily_XYZ present in response", "TestFamily_XYZ" in names)
            self.runner.assert_true("TestFamily_XYZ got an auto-assigned FamilyID", new_id is not None, f"FamilyID={new_id}")

        # 2b. Duplicate family name → 400
        dup_name_list = current + [new_entry, {**new_entry, "FamilyID": None}]
        r = self.session.post(self._url("UpdateMesFamilies"), json=dup_name_list)
        self.runner.assert_status("duplicate family name → 400", r, 400)

        # 2c. Duplicate FamilyID → 400
        after_add = self._get_families()
        if len(after_add) >= 2:
            dup_id_list = json.loads(json.dumps(after_add))
            dup_id_list[1]["FamilyID"] = dup_id_list[0]["FamilyID"]
            r = self.session.post(self._url("UpdateMesFamilies"), json=dup_id_list)
            self.runner.assert_status("duplicate FamilyID → 400", r, 400)

        # 2d. Remove TestFamily_XYZ (send original 6)
        r = self.session.post(self._url("UpdateMesFamilies"), json=current)
        ok = self.runner.assert_status("remove TestFamily_XYZ → 200", r, 200)
        if ok:
            final_names = [f["Family"] for f in r.json().get("Families", [])]
            self.runner.assert_true(
                "TestFamily_XYZ no longer in family list",
                "TestFamily_XYZ" not in final_names,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 3 — GetMesTemplates
# ─────────────────────────────────────────────────────────────────────────────
class TestGetMesTemplates(BaseTestGroup):
    def run(self):
        print("\n── Group 3: GET /GetMesTemplates/{mes_family} ──")

        r = self.session.get(self._url("GetMesTemplates/FAB300"))
        ok = self.runner.assert_status("FAB300 → 200", r, 200)
        if ok:
            templates = r.json()
            has_seed = any("STANDARD_EVENT_MODEL" in t for t in templates)
            self.runner.assert_true("STANDARD_EVENT_MODEL seeded in FAB300", has_seed)

        r = self.session.get(self._url("GetMesTemplates/NonExistentFamily_XYZZY"))
        self.runner.assert_status("nonexistent family → 404", r, 404)


# ─────────────────────────────────────────────────────────────────────────────
# Group 4 — GetMesTemplateInfo
# ─────────────────────────────────────────────────────────────────────────────
class TestGetMesTemplateInfo(BaseTestGroup):
    REQUIRED_KEYS = [
        "Events", "Alarms", "Variables", "Payloads",
        "Transactions", "ValidationRules", "AutoMapping", "Logging",
    ]

    def run(self):
        print("\n── Group 4: GET /GetMesTemplateInfo/{mes_family}/{template} ──")

        r = self.session.get(self._url("GetMesTemplateInfo/FAB300/STANDARD_EVENT_MODEL"))
        ok = self.runner.assert_status("FAB300/STANDARD_EVENT_MODEL → 200", r, 200)
        if ok:
            body = r.json()
            missing = [k for k in self.REQUIRED_KEYS if k not in body]
            self.runner.assert_true(
                "template has all required top-level keys",
                not missing,
                f"missing: {missing}" if missing else "",
            )

        r = self.session.get(self._url("GetMesTemplateInfo/FAB300/ghost_template_XYZZY"))
        self.runner.assert_status("nonexistent template → 404", r, 404)

        r = self.session.get(self._url("GetMesTemplateInfo/FakeFamily_XYZZY/STANDARD_EVENT_MODEL"))
        self.runner.assert_status("nonexistent family → 404", r, 404)


# ─────────────────────────────────────────────────────────────────────────────
# Group 5 — AddMesTemplateInfo
# ─────────────────────────────────────────────────────────────────────────────
class TestAddMesTemplateInfo(BaseTestGroup):
    def run(self):
        print("\n── Group 5: POST /AddMesTemplateInfo/{mes_family} ──")
        payload = self._make_template("FAB300", TEST_TEMPLATE_NAME)

        # 5a. Valid upload
        r = self._upload_template("FAB300", f"{TEST_TEMPLATE_NAME}.json", payload)
        self.runner.assert_status("valid upload → 200", r, 200)

        # 5b. Duplicate → 409
        r = self._upload_template("FAB300", f"{TEST_TEMPLATE_NAME}.json", payload)
        self.runner.assert_status("duplicate upload → 409", r, 409)

        # 5c. Non-.json file → 400
        r = self._upload_template("FAB300", "bad_file.txt", b"not json at all", "text/plain")
        self.runner.assert_status("non-.json file → 400", r, 400)

        # 5d. Invalid JSON bytes → 400
        r = self._upload_template("FAB300", "invalid.json", b"{this is not valid json!!!}")
        self.runner.assert_status("invalid JSON bytes → 400", r, 400)

        # 5e. Mismatched MESFamily → 422
        wrong = self._make_template("PROMIS", TEST_TEMPLATE_NAME)
        r = self._upload_template("FAB300", f"{TEST_TEMPLATE_NAME}_mismatch.json", wrong)
        self.runner.assert_status("mismatched MESFamily in body → 422", r, 422)

        # 5f. Nonexistent family → 404
        r = self._upload_template("FakeFamily_XYZZY", f"{TEST_TEMPLATE_NAME}.json", payload)
        self.runner.assert_status("upload to nonexistent family → 404", r, 404)


# ─────────────────────────────────────────────────────────────────────────────
# Group 6 — UpdateMesTemplateInfo
# ─────────────────────────────────────────────────────────────────────────────
class TestUpdateMesTemplateInfo(BaseTestGroup):
    def _ensure_test_template_exists(self):
        existing = self.session.get(self._url("GetMesTemplates/FAB300")).json()
        if f"{TEST_TEMPLATE_NAME}.json" not in existing:
            payload = self._make_template("FAB300", TEST_TEMPLATE_NAME)
            self._upload_template("FAB300", f"{TEST_TEMPLATE_NAME}.json", payload)

    def run(self):
        print("\n── Group 6: PUT /UpdateMesTemplateInfo/{mes_family}/{template} ──")
        self._ensure_test_template_exists()

        # 6a. No Version supplied → auto-increment to 1.1
        updated = self._make_template("FAB300", TEST_TEMPLATE_NAME)
        del updated["Version"]
        updated["Description"] = "Updated description"
        r = self._update_template("FAB300", TEST_TEMPLATE_NAME, updated)
        ok = self.runner.assert_status("valid update (no Version) → 200", r, 200)
        if ok:
            v = r.json().get("Version", "")
            self.runner.assert_true(
                "version auto-incremented to 1.1",
                v == "1.1",
                f"got '{v}'",
            )

        # 6b. Explicit Version → preserved as-is
        explicit = self._make_template("FAB300", TEST_TEMPLATE_NAME)
        explicit["Version"] = "3.0"
        r = self._update_template("FAB300", TEST_TEMPLATE_NAME, explicit)
        ok = self.runner.assert_status("update with explicit Version='3.0' → 200", r, 200)
        if ok:
            v = r.json().get("Version", "")
            self.runner.assert_true("version preserved as '3.0'", v == "3.0", f"got '{v}'")

        # 6c. Mismatched MESFamily → 422
        mismatch = self._make_template("PROMIS", TEST_TEMPLATE_NAME)
        r = self._update_template("FAB300", TEST_TEMPLATE_NAME, mismatch)
        self.runner.assert_status("mismatched MESFamily → 422", r, 422)

        # 6d. Nonexistent template → 404
        r = self._update_template("FAB300", "ghost_template_XYZZY", self._make_template("FAB300", "ghost"))
        self.runner.assert_status("nonexistent template → 404", r, 404)

        # 6e. Non-.json filename → 400
        data = json.dumps(self._make_template("FAB300", TEST_TEMPLATE_NAME)).encode()
        files = {"file": ("bad.txt", io.BytesIO(data), "text/plain")}
        r = self.session.put(self._url(f"UpdateMesTemplateInfo/FAB300/{TEST_TEMPLATE_NAME}"), files=files)
        self.runner.assert_status("non-.json file → 400", r, 400)


# ─────────────────────────────────────────────────────────────────────────────
# MesApiTestSuite  —  orchestrates all groups
# ─────────────────────────────────────────────────────────────────────────────
class MesApiTestSuite:
    def __init__(self, base_url: str = BASE_URL, verbose: bool = False):
        self.base_url = base_url
        self.runner = TestRunner(verbose=verbose)
        self.session = requests.Session()
        self._groups = [
            TestGetMesFamilies,
            TestUpdateMesFamilies,
            TestGetMesTemplates,
            TestGetMesTemplateInfo,
            TestAddMesTemplateInfo,
            TestUpdateMesTemplateInfo,
        ]

    def _check_server(self):
        try:
            self.session.get(f"{self.base_url}/health", timeout=5)
        except Exception as e:
            print(f"\n❌  Cannot reach server at {self.base_url}: {e}")
            sys.exit(1)

    def _cleanup_note(self):
        print("\n── Cleanup note ──")
        print(f"  ℹ️  '{TEST_TEMPLATE_NAME}.json' was created in MESMapTemplates/FAB300/.")
        print("     Delete it manually for a clean slate, or re-run safely — duplicates are handled.")

    def run(self):
        print(f"\n{'='*60}")
        print(f"  MES Family API Test Suite")
        print(f"  Target: {self.base_url}")
        print(f"{'='*60}")

        self._check_server()

        for GroupClass in self._groups:
            GroupClass(self.runner, self.session, self.base_url).run()

        self._cleanup_note()
        self.runner.summary()
        sys.exit(0 if self.runner.failed == 0 else 1)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MES Family API test suite")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print response body on every call")
    parser.add_argument("--url", default=BASE_URL, help="Override base URL")
    args = parser.parse_args()

    MesApiTestSuite(base_url=args.url, verbose=args.verbose).run()
