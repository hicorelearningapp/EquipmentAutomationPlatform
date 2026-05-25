"""
test_mes_family_api.py
======================
Test suite for the 6 MES Family / Template endpoints.

Every test follows the same pattern:
    REQUEST  — what we send (method, URL, payload/file)
    RESPONSE — what we assert (status code + specific body fields)

Endpoints covered
-----------------
  GET  /GetMesFamilies
  POST /UpdateMesFamilies
  GET  /GetMesTemplates/{mes_family}
  GET  /GetMesTemplateInfo/{mes_family}/{template}
  POST /AddMesTemplateInfo/{mes_family}
  PUT  /UpdateMesTemplateInfo/{mes_family}/{template}

Usage
-----
  python test_mes_family_api.py              # run against default server
  python test_mes_family_api.py -v           # verbose: print response body on every call
  python test_mes_family_api.py --url http://localhost:8000
"""

import argparse
import io
import json
import sys

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "http://151.185.41.194:8012"

# These 6 families are seeded at server startup via mes_family_seed.py.
# Every GET test that needs a real family uses one of these.
SEEDED_FAMILIES = [
    "FactoryWorks",
    "FAB300",
    "PROMIS",
    "Camstar",
    "Critical Manufacturing",
    "Custom MES",
]

# Name used for templates created during tests.
# Chosen to be obviously synthetic so it never collides with real data.
TEST_TEMPLATE_NAME = "TEST_AUTO_TEMPLATE_DO_NOT_USE"

# Family used as the upload/update target for template tests.
TARGET_FAMILY = "FAB300"

# Temporary family name used in UpdateMesFamilies tests.
TEMP_FAMILY_NAME = "TestFamily_TEMP_XYZ"


# ─────────────────────────────────────────────────────────────────────────────
# TestRunner  —  counts pass / fail, prints structured output
# ─────────────────────────────────────────────────────────────────────────────

class TestRunner:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.passed = 0
        self.failed = 0

    def check_status(
        self,
        label: str,
        response: requests.Response,
        expected_status: int,
    ) -> bool:
        """Assert the HTTP status code. Always the first assertion in every test."""
        ok = response.status_code == expected_status
        symbol = "✅" if ok else "❌"
        print(f"  {symbol}  [{response.status_code} expected {expected_status}]  {label}")
        if not ok or self.verbose:
            self._print_body(response)
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        return ok

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        """Assert any boolean condition on the response body."""
        symbol = "✅" if condition else "❌"
        suffix = f"  ({detail})" if detail else ""
        print(f"       {'↳'} {symbol}  {label}{suffix}")
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def _print_body(self, response: requests.Response) -> None:
        try:
            body = json.dumps(response.json(), indent=2)
        except Exception:
            body = response.text
        print(f"         Response body: {body[:500]}")

    def summary(self) -> None:
        total = self.passed + self.failed
        status = "ALL PASSED" if self.failed == 0 else f"{self.failed} FAILED"
        print(f"\n{'=' * 60}")
        print(f"  {status}  —  {self.passed}/{total} assertions passed")
        print(f"{'=' * 60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# BaseTestGroup  —  shared HTTP session and helpers
# ─────────────────────────────────────────────────────────────────────────────

class BaseTestGroup:
    def __init__(self, runner: TestRunner, session: requests.Session, base_url: str):
        self.r = runner
        self.s = session
        self.base = base_url.rstrip("/")

    # ── URL builder ───────────────────────────────────────────────────────────

    def url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    # ── Common payload factories ──────────────────────────────────────────────

    def _template_payload(self, mes_family: str, template_name: str) -> dict:
        """Minimal valid template body that satisfies all server-side checks."""
        return {
            "MESFamily": mes_family,
            "TemplateName": template_name,
            "Version": "1.0",
            "Description": "Automated test template — safe to delete",
            "Events": [],
            "Alarms": [],
            "Variables": [],
            "Payloads": [],
            "Transactions": [],
            "ValidationRules": [],
            "AutoMapping": {"Enabled": True},
            "Logging": {"Enabled": True},
        }

    # ── HTTP helpers ──────────────────────────────────────────────────────────

    def _upload_template(
        self,
        mes_family: str,
        filename: str,
        payload,               # dict → serialised to JSON bytes; bytes → sent raw
        content_type: str = "application/json",
    ) -> requests.Response:
        """POST /AddMesTemplateInfo/{mes_family} with a file upload."""
        data = json.dumps(payload).encode() if isinstance(payload, dict) else payload
        files = {"file": (filename, io.BytesIO(data), content_type)}
        return self.s.post(self.url(f"AddMesTemplateInfo/{mes_family}"), files=files)

    def _update_template(
        self,
        mes_family: str,
        template: str,
        payload: dict,
        filename: str = None,
        content_type: str = "application/json",
    ) -> requests.Response:
        """PUT /UpdateMesTemplateInfo/{mes_family}/{template} with a file upload."""
        fname = filename or f"{template}.json"
        data = json.dumps(payload).encode()
        files = {"file": (fname, io.BytesIO(data), content_type)}
        return self.s.put(
            self.url(f"UpdateMesTemplateInfo/{mes_family}/{template}"), files=files
        )

    def _current_families(self) -> list:
        """Fetch the live families list. Raises on HTTP error."""
        r = self.s.get(self.url("GetMesFamilies"))
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("MESFamilies", [])

    def _ensure_template_exists(self, mes_family: str, template_name: str) -> None:
        """Upload the test template if it is not already present."""
        existing = self.s.get(self.url(f"GetMesTemplates/{mes_family}")).json()
        if f"{template_name}.json" not in existing:
            payload = self._template_payload(mes_family, template_name)
            self._upload_template(mes_family, f"{template_name}.json", payload)

    def run(self):
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — GET /GetMesFamilies
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMesFamilies(BaseTestGroup):
    """
    Tests
    -----
    1a  Happy path — returns 200 with a list
    1b  Response body — all 6 seeded families are present
    1c  Response body — every entry has the required keys
    """

    def run(self):
        print("\n── Group 1: GET /GetMesFamilies ─────────────────────────────")

        # REQUEST:  GET /GetMesFamilies   (no body, no params)
        response = self.s.get(self.url("GetMesFamilies"))

        # RESPONSE: status
        ok = self.r.check_status("returns 200", response, 200)
        if not ok:
            return

        families = response.json()
        if isinstance(families, dict):
            families = families.get("MESFamilies", [])

        names = [f.get("Family") for f in families]

        # RESPONSE: body — all seeded names present
        missing_names = [s for s in SEEDED_FAMILIES if s not in names]
        self.r.check(
            "all 6 seeded families present",
            not missing_names,
            f"missing: {missing_names}" if missing_names else "",
        )

        # RESPONSE: body — every entry has required schema keys
        required_keys = {"Family", "DefaultProtocol", "RequiresAck", "Description"}
        entries_missing_keys = [
            f.get("Family", "?")
            for f in families
            if not required_keys.issubset(f.keys())
        ]
        self.r.check(
            "every entry has Family / DefaultProtocol / RequiresAck / Description",
            not entries_missing_keys,
            f"incomplete entries: {entries_missing_keys}" if entries_missing_keys else "",
        )

        # RESPONSE: body — FamilyID is set on all seeded entries
        missing_ids = [f.get("Family") for f in families if f.get("FamilyID") is None]
        self.r.check(
            "all entries have a non-null FamilyID",
            not missing_ids,
            f"missing IDs: {missing_ids}" if missing_ids else "",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — POST /UpdateMesFamilies
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateMesFamilies(BaseTestGroup):
    """
    Tests
    -----
    2a  Add a new family → 200, new family present in response, FamilyID assigned
    2b  Duplicate family name in request body → 400, detail mentions duplicate
    2c  Duplicate FamilyID in request body → 400
    2d  Remove the test family (restore original list) → 200, name absent from response
    """

    def run(self):
        print("\n── Group 2: POST /UpdateMesFamilies ─────────────────────────")

        current = self._current_families()

        # ── 2a  Add new family ────────────────────────────────────────────────
        new_entry = {
            "FamilyID": None,
            "Family": TEMP_FAMILY_NAME,
            "DefaultProtocol": "REST/JSON",
            "RequiresAck": False,
            "Description": "Temporary family created by automated test",
        }

        # REQUEST:  POST /UpdateMesFamilies — existing list + 1 new entry
        response = self.s.post(self.url("UpdateMesFamilies"), json=current + [new_entry])

        # RESPONSE: status
        ok = self.r.check_status("add new family → 200", response, 200)
        if ok:
            body = response.json()
            returned_families = body.get("Families", [])
            returned_names = [f["Family"] for f in returned_families]
            new_id = next(
                (f["FamilyID"] for f in returned_families if f["Family"] == TEMP_FAMILY_NAME),
                None,
            )

            # RESPONSE: body — new family appears by name
            self.r.check(
                f"'{TEMP_FAMILY_NAME}' present in response Families list",
                TEMP_FAMILY_NAME in returned_names,
                f"found: {returned_names}",
            )
            # RESPONSE: body — auto-assigned a FamilyID
            self.r.check(
                f"'{TEMP_FAMILY_NAME}' received an auto-assigned FamilyID",
                new_id is not None,
                f"FamilyID={new_id}",
            )
            # RESPONSE: body — Status field
            self.r.check(
                "response Status is 'success'",
                body.get("Status") == "success",
                f"Status='{body.get('Status')}'",
            )

        # ── 2b  Duplicate family name → 400 ──────────────────────────────────
        dup_name_list = current + [new_entry, {**new_entry, "FamilyID": None}]

        # REQUEST:  POST /UpdateMesFamilies — two entries with the same Family name
        response = self.s.post(self.url("UpdateMesFamilies"), json=dup_name_list)

        # RESPONSE: status
        ok = self.r.check_status("duplicate family name → 400", response, 400)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error message mentions "duplicate"
            self.r.check(
                "error detail mentions 'duplicate'",
                "duplicate" in detail,
                f"detail: {detail[:120]}",
            )

        # ── 2c  Duplicate FamilyID → 400 ─────────────────────────────────────
        after_add = self._current_families()
        if len(after_add) >= 2:
            dup_id_list = json.loads(json.dumps(after_add))   # deep copy
            dup_id_list[1]["FamilyID"] = dup_id_list[0]["FamilyID"]

            # REQUEST:  POST /UpdateMesFamilies — two entries sharing the same FamilyID
            response = self.s.post(self.url("UpdateMesFamilies"), json=dup_id_list)

            # RESPONSE: status
            ok = self.r.check_status("duplicate FamilyID → 400", response, 400)
            if ok:
                detail = str(response.json()).lower()
                # RESPONSE: body — error message mentions "duplicate"
                self.r.check(
                    "error detail mentions 'duplicate'",
                    "duplicate" in detail,
                    f"detail: {detail[:120]}",
                )

        # ── 2d  Delete the temp family (restore original 6) ──────────────────

        # REQUEST:  POST /UpdateMesFamilies — original list only (no TEMP_FAMILY_NAME)
        response = self.s.post(self.url("UpdateMesFamilies"), json=current)

        # RESPONSE: status
        ok = self.r.check_status("remove temp family → 200", response, 200)
        if ok:
            final_names = [f["Family"] for f in response.json().get("Families", [])]
            # RESPONSE: body — temp family is gone
            self.r.check(
                f"'{TEMP_FAMILY_NAME}' no longer in Families list",
                TEMP_FAMILY_NAME not in final_names,
                f"found: {final_names}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 3 — GET /GetMesTemplates/{mes_family}
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMesTemplates(BaseTestGroup):
    """
    Tests
    -----
    3a  Known family → 200, list contains at least STANDARD_EVENT_MODEL.json
    3b  Unknown family → 404, detail mentions the family name
    3c  Known family that has no user-added templates still returns a list (not an error)
    """

    def run(self):
        print("\n── Group 3: GET /GetMesTemplates/{mes_family} ───────────────")

        # ── 3a  Known family ──────────────────────────────────────────────────

        # REQUEST:  GET /GetMesTemplates/FAB300
        response = self.s.get(self.url(f"GetMesTemplates/{TARGET_FAMILY}"))

        # RESPONSE: status
        ok = self.r.check_status(f"known family ({TARGET_FAMILY}) → 200", response, 200)
        if ok:
            templates = response.json()
            # RESPONSE: body — response is a list
            self.r.check(
                "response is a list",
                isinstance(templates, list),
                f"type: {type(templates).__name__}",
            )
            # RESPONSE: body — seeded STANDARD_EVENT_MODEL.json is present
            has_seed = any("STANDARD_EVENT_MODEL" in t for t in templates)
            self.r.check(
                "STANDARD_EVENT_MODEL.json is present (seeded at startup)",
                has_seed,
                f"files found: {templates}",
            )

        # ── 3b  Unknown family → 404 ──────────────────────────────────────────

        # REQUEST:  GET /GetMesTemplates/NonExistentFamily_XYZZY
        response = self.s.get(self.url("GetMesTemplates/NonExistentFamily_XYZZY"))

        # RESPONSE: status
        ok = self.r.check_status("unknown family → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error message references the unknown name
            self.r.check(
                "error detail mentions the unknown family name",
                "nonexistentfamily_xyzzy" in detail,
                f"detail: {detail[:120]}",
            )

        # ── 3c  Known family with no extra templates → 200, empty or non-empty list ──
        # We use "Custom MES" which exists but is unlikely to have extra templates.

        # REQUEST:  GET /GetMesTemplates/Custom MES   (space encoded by requests)
        response = self.s.get(self.url("GetMesTemplates/Custom MES"))

        # RESPONSE: status  (200 whether templates exist or not)
        ok = self.r.check_status("known family with possibly no templates → 200", response, 200)
        if ok:
            templates = response.json()
            # RESPONSE: body — must be a list (empty is fine)
            self.r.check(
                "response is a list (empty list is acceptable)",
                isinstance(templates, list),
                f"type: {type(templates).__name__}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 4 — GET /GetMesTemplateInfo/{mes_family}/{template}
# ─────────────────────────────────────────────────────────────────────────────

class TestGetMesTemplateInfo(BaseTestGroup):
    """
    Tests
    -----
    4a  Valid family + valid template → 200, body has expected top-level keys
    4b  Valid family + nonexistent template → 404
    4c  Nonexistent family → 404
    4d  Template name without .json extension → auto-appended → 200
    """

    EXPECTED_KEYS = {
        "Events", "Alarms", "Variables", "Payloads",
        "Transactions", "ValidationRules", "AutoMapping", "Logging",
    }

    def run(self):
        print("\n── Group 4: GET /GetMesTemplateInfo/{mes_family}/{template} ─")

        # ── 4a  Valid family + valid template ─────────────────────────────────

        # REQUEST:  GET /GetMesTemplateInfo/FAB300/STANDARD_EVENT_MODEL.json
        response = self.s.get(
            self.url(f"GetMesTemplateInfo/{TARGET_FAMILY}/STANDARD_EVENT_MODEL.json")
        )

        # RESPONSE: status
        ok = self.r.check_status(
            f"{TARGET_FAMILY}/STANDARD_EVENT_MODEL.json → 200", response, 200
        )
        if ok:
            body = response.json()
            # RESPONSE: body — all expected top-level keys present
            missing = self.EXPECTED_KEYS - body.keys()
            self.r.check(
                "body contains all required top-level keys",
                not missing,
                f"missing: {missing}" if missing else "",
            )

        # ── 4b  Valid family + nonexistent template → 404 ────────────────────

        # REQUEST:  GET /GetMesTemplateInfo/FAB300/ghost_XYZZY.json
        response = self.s.get(
            self.url(f"GetMesTemplateInfo/{TARGET_FAMILY}/ghost_XYZZY.json")
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent template → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions the template name
            self.r.check(
                "error detail mentions the template name",
                "ghost_xyzzy" in detail,
                f"detail: {detail[:120]}",
            )

        # ── 4c  Nonexistent family → 404 ─────────────────────────────────────

        # REQUEST:  GET /GetMesTemplateInfo/FakeFamily_XYZZY/STANDARD_EVENT_MODEL.json
        response = self.s.get(
            self.url("GetMesTemplateInfo/FakeFamily_XYZZY/STANDARD_EVENT_MODEL.json")
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent family → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions the family name
            self.r.check(
                "error detail mentions the family name",
                "fakefamily_xyzzy" in detail,
                f"detail: {detail[:120]}",
            )

        # ── 4d  No .json extension → server auto-appends it → 200 ────────────

        # REQUEST:  GET /GetMesTemplateInfo/FAB300/STANDARD_EVENT_MODEL  (no .json)
        response = self.s.get(
            self.url(f"GetMesTemplateInfo/{TARGET_FAMILY}/STANDARD_EVENT_MODEL")
        )

        # RESPONSE: status  (server appends .json internally)
        ok = self.r.check_status(
            "template name without .json extension auto-resolved → 200", response, 200
        )
        if ok:
            body = response.json()
            # RESPONSE: body — same keys as 4a
            missing = self.EXPECTED_KEYS - body.keys()
            self.r.check(
                "body contains all required top-level keys",
                not missing,
                f"missing: {missing}" if missing else "",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 5 — POST /AddMesTemplateInfo/{mes_family}
# ─────────────────────────────────────────────────────────────────────────────

class TestAddMesTemplateInfo(BaseTestGroup):
    """
    Tests
    -----
    5a  Valid JSON upload → 200, Status=success
    5b  Duplicate upload (same filename) → 409, detail mentions conflict
    5c  Non-.json filename → 400, detail mentions file type
    5d  Syntactically invalid JSON bytes → 400
    5e  MESFamily in payload doesn't match URL family → 422
    5f  Upload to nonexistent family → 404
    """

    def run(self):
        print("\n── Group 5: POST /AddMesTemplateInfo/{mes_family} ───────────")

        # Prepare the nominal payload (MESFamily matches TARGET_FAMILY)
        payload = self._template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)

        # ── 5a  Valid upload ──────────────────────────────────────────────────

        # REQUEST:  POST /AddMesTemplateInfo/FAB300  —  valid .json file
        response = self._upload_template(
            TARGET_FAMILY, f"{TEST_TEMPLATE_NAME}.json", payload
        )

        # RESPONSE: status
        ok = self.r.check_status("valid upload → 200", response, 200)
        if ok:
            body = response.json()
            # RESPONSE: body — Status field
            self.r.check(
                "response Status is 'success'",
                body.get("Status") == "success",
                f"Status='{body.get('Status')}'",
            )
            # RESPONSE: body — Message mentions the template name
            msg = body.get("Message", "").lower()
            self.r.check(
                "Message mentions the uploaded template name",
                TEST_TEMPLATE_NAME.lower() in msg,
                f"Message: {msg[:120]}",
            )

        # ── 5b  Duplicate upload → 409 ────────────────────────────────────────

        # REQUEST:  POST /AddMesTemplateInfo/FAB300  —  same filename again
        response = self._upload_template(
            TARGET_FAMILY, f"{TEST_TEMPLATE_NAME}.json", payload
        )

        # RESPONSE: status
        ok = self.r.check_status("duplicate upload → 409", response, 409)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions conflict / already exists
            self.r.check(
                "error detail mentions 'already exists' or 'conflict'",
                any(kw in detail for kw in ("already exists", "conflict", "exist")),
                f"detail: {detail[:120]}",
            )

        # ── 5c  Non-.json filename → 400 ─────────────────────────────────────

        # REQUEST:  POST /AddMesTemplateInfo/FAB300  —  .txt file (wrong type)
        response = self._upload_template(
            TARGET_FAMILY, "wrong_extension.txt", b"not json", "text/plain"
        )

        # RESPONSE: status
        ok = self.r.check_status("non-.json file → 400", response, 400)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions file type / .json requirement
            self.r.check(
                "error detail mentions '.json' or file type",
                any(kw in detail for kw in (".json", "json", "file")),
                f"detail: {detail[:120]}",
            )

        # ── 5d  Invalid JSON bytes → 400 ─────────────────────────────────────

        # REQUEST:  POST /AddMesTemplateInfo/FAB300  —  malformed JSON content
        response = self._upload_template(
            TARGET_FAMILY, "malformed.json", b"{this is NOT valid json!!!}"
        )

        # RESPONSE: status
        ok = self.r.check_status("malformed JSON content → 400", response, 400)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions JSON / parse problem
            self.r.check(
                "error detail mentions JSON parse failure",
                any(kw in detail for kw in ("json", "invalid", "parse")),
                f"detail: {detail[:120]}",
            )

        # ── 5e  Mismatched MESFamily in payload → 422 ────────────────────────
        wrong_family_payload = self._template_payload("PROMIS", TEST_TEMPLATE_NAME)

        # REQUEST:  POST /AddMesTemplateInfo/FAB300  —  MESFamily='PROMIS' in body
        response = self._upload_template(
            TARGET_FAMILY,
            f"{TEST_TEMPLATE_NAME}_mismatch.json",
            wrong_family_payload,
        )

        # RESPONSE: status
        ok = self.r.check_status("MESFamily mismatch in payload → 422", response, 422)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions the mismatch
            self.r.check(
                "error detail mentions family name mismatch",
                any(kw in detail for kw in ("match", "family", "mismatch", "does not")),
                f"detail: {detail[:120]}",
            )

        # ── 5f  Nonexistent family → 404 ─────────────────────────────────────

        # REQUEST:  POST /AddMesTemplateInfo/GhostFamily_XYZZY
        response = self._upload_template(
            "GhostFamily_XYZZY",
            f"{TEST_TEMPLATE_NAME}.json",
            self._template_payload("GhostFamily_XYZZY", TEST_TEMPLATE_NAME),
        )

        # RESPONSE: status
        ok = self.r.check_status("upload to nonexistent family → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions the unknown family
            self.r.check(
                "error detail mentions the unknown family name",
                "ghostfamily_xyzzy" in detail,
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 6 — PUT /UpdateMesTemplateInfo/{mes_family}/{template}
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateMesTemplateInfo(BaseTestGroup):
    """
    Tests
    -----
    6a  Valid update, no Version supplied → 200, version auto-incremented to 1.1
    6b  Valid update, explicit Version='3.0' → 200, version preserved as '3.0'
    6c  MESFamily in payload doesn't match URL family → 422
    6d  Nonexistent template → 404
    6e  Non-.json filename → 400
    6f  Syntactically invalid JSON bytes → 400
    """

    def run(self):
        print("\n── Group 6: PUT /UpdateMesTemplateInfo/{mes_family}/{template}")

        # Ensure the test template exists before running update tests
        self._ensure_template_exists(TARGET_FAMILY, TEST_TEMPLATE_NAME)

        # ── 6a  No Version → auto-incremented ────────────────────────────────
        updated_payload = self._template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)
        del updated_payload["Version"]             # omit so server auto-increments
        updated_payload["Description"] = "Updated by automated test"

        # REQUEST:  PUT /UpdateMesTemplateInfo/FAB300/TEST_AUTO_TEMPLATE_DO_NOT_USE
        #           file body: valid JSON without a Version field
        response = self._update_template(TARGET_FAMILY, TEST_TEMPLATE_NAME, updated_payload)

        # RESPONSE: status
        ok = self.r.check_status("valid update, no Version → 200", response, 200)
        if ok:
            body = response.json()
            version = body.get("Version", "")
            # RESPONSE: body — version should have been incremented from 1.0 to 1.1
            self.r.check(
                "Version auto-incremented to '1.1'",
                version == "1.1",
                f"got Version='{version}'",
            )
            # RESPONSE: body — Status field
            self.r.check(
                "response Status is 'success'",
                body.get("Status") == "success",
                f"Status='{body.get('Status')}'",
            )

        # ── 6b  Explicit Version preserved ───────────────────────────────────
        explicit_payload = self._template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)
        explicit_payload["Version"] = "3.0"

        # REQUEST:  PUT same endpoint — payload includes Version='3.0'
        response = self._update_template(TARGET_FAMILY, TEST_TEMPLATE_NAME, explicit_payload)

        # RESPONSE: status
        ok = self.r.check_status("explicit Version='3.0' → 200", response, 200)
        if ok:
            version = response.json().get("Version", "")
            # RESPONSE: body — version must stay exactly '3.0'
            self.r.check(
                "Version preserved as '3.0'",
                version == "3.0",
                f"got Version='{version}'",
            )

        # ── 6c  MESFamily mismatch → 422 ─────────────────────────────────────
        mismatch_payload = self._template_payload("PROMIS", TEST_TEMPLATE_NAME)

        # REQUEST:  PUT FAB300/TEST_TEMPLATE — payload says MESFamily='PROMIS'
        response = self._update_template(TARGET_FAMILY, TEST_TEMPLATE_NAME, mismatch_payload)

        # RESPONSE: status
        ok = self.r.check_status("MESFamily mismatch → 422", response, 422)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions mismatch
            self.r.check(
                "error detail mentions family name mismatch",
                any(kw in detail for kw in ("match", "family", "mismatch", "does not")),
                f"detail: {detail[:120]}",
            )

        # ── 6d  Nonexistent template → 404 ───────────────────────────────────
        ghost_payload = self._template_payload(TARGET_FAMILY, "ghost_template_XYZZY")

        # REQUEST:  PUT FAB300/ghost_template_XYZZY — template does not exist on disk
        response = self._update_template(TARGET_FAMILY, "ghost_template_XYZZY", ghost_payload)

        # RESPONSE: status
        ok = self.r.check_status("nonexistent template → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions the template name
            self.r.check(
                "error detail mentions the template name",
                "ghost_template_xyzzy" in detail,
                f"detail: {detail[:120]}",
            )

        # ── 6e  Non-.json filename → 400 ─────────────────────────────────────

        # REQUEST:  PUT FAB300/TEST_TEMPLATE — file uploaded with .txt extension
        response = self._update_template(
            TARGET_FAMILY,
            TEST_TEMPLATE_NAME,
            self._template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME),
            filename="wrong_extension.txt",
            content_type="text/plain",
        )

        # RESPONSE: status
        ok = self.r.check_status("non-.json filename → 400", response, 400)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions .json / file type
            self.r.check(
                "error detail mentions '.json' or file type",
                any(kw in detail for kw in (".json", "json", "file")),
                f"detail: {detail[:120]}",
            )

        # ── 6f  Malformed JSON bytes → 400 ───────────────────────────────────
        bad_bytes = b"{this is not json!}"
        files = {"file": (f"{TEST_TEMPLATE_NAME}.json", io.BytesIO(bad_bytes), "application/json")}

        # REQUEST:  PUT FAB300/TEST_TEMPLATE — file content is not valid JSON
        response = self.s.put(
            self.url(f"UpdateMesTemplateInfo/{TARGET_FAMILY}/{TEST_TEMPLATE_NAME}"),
            files=files,
        )

        # RESPONSE: status
        ok = self.r.check_status("malformed JSON content → 400", response, 400)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions JSON parse failure
            self.r.check(
                "error detail mentions JSON parse failure",
                any(kw in detail for kw in ("json", "invalid", "parse")),
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# MesApiTestSuite  —  orchestrates all groups in order
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

    def _check_server(self) -> None:
        try:
            r = self.session.get(f"{self.base_url}/health", timeout=5)
            r.raise_for_status()
        except Exception as e:
            print(f"\n❌  Cannot reach server at {self.base_url}: {e}")
            sys.exit(1)

    def _cleanup_note(self) -> None:
        print("\n── Cleanup note ─────────────────────────────────────────────")
        print(f"  ℹ️  '{TEST_TEMPLATE_NAME}.json' was created in MESMapTemplates/{TARGET_FAMILY}/")
        print("     It is safe to delete. Re-running the suite is also safe — duplicates are handled.")

    def run(self) -> None:
        print(f"\n{'=' * 60}")
        print(f"  MES Family API  —  Test Suite")
        print(f"  Target : {self.base_url}")
        print(f"  Groups : {len(self._groups)}")
        print(f"{'=' * 60}")

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
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print response body after every assertion, not just on failure",
    )
    parser.add_argument(
        "--url",
        default=BASE_URL,
        help=f"Override base URL (default: {BASE_URL})",
    )
    args = parser.parse_args()

    MesApiTestSuite(base_url=args.url, verbose=args.verbose).run()