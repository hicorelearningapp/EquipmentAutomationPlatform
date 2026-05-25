"""
test_documents_api.py
=====================
Test suite for all 7 Documents endpoints.

Every test follows the same pattern:
    REQUEST  — what we send (method, URL, payload / file / params)
    RESPONSE — what we assert (status code + specific body fields)

Endpoints covered
-----------------
  POST   /UploadDocument/{project_id}
  GET    /Analyze/{project_id}/{document_id}
  GET    /AnalyzeProject/{project_id}
  GET    /Analyze/{project_id}/{document_id}/report
  GET    /GetVariable/{project_id}/{document_id}
  DELETE /DeleteDocument/{project_id}/{document_id}
  POST   /UpdateExtraction/{project_id}

Execution order
---------------
  Suite Setup    — create a temp project via POST /AddProject
  Group 1        — UploadDocument  (upload PDF, xlsx, txt, bad types, duplicates, 404s)
  Group 2        — Analyze         (uses already-uploaded PDF; TRIGGERS LLM — may take 30–90 s)
  Group 3        — AnalyzeProject  (aggregated run on the same project)
  Group 4        — DownloadReport  (on the completed document)
  Group 5        — GetVariable     (category filtering, invalid inputs, 404s)
  Group 6        — DeleteDocument  (delete + verify gone)
  Group 7        — UpdateExtraction
  Suite Teardown — delete the temp project via DELETE /DeleteProject/{id}

Usage
-----
  python test_documents_api.py                        # normal
  python test_documents_api.py -v                     # verbose: print body on every call
  python test_documents_api.py --url http://localhost:8000
  python test_documents_api.py --pdf path/to/file.pdf # use your own PDF (recommended)

Notes
-----
  * If no --pdf is supplied, the suite generates a minimal synthetic PDF on the fly
    using only the stdlib. It will be tiny and may produce an empty extraction,
    but all structural / error-path tests will still pass.
  * Analyze (Group 2) is the only slow test. All other groups reuse the result.
"""

import argparse
import io
import json
import struct
import sys
import zlib

import requests


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = "http://151.185.41.194:8012"

# DocumentCategory enum values (from source/schemas/project.py)
DOC_CATEGORY_GEM    = "GEM Manual"
DOC_CATEGORY_USER   = "User Manuals"
DOC_CATEGORY_VAR    = "Variable Files"
DOC_CATEGORY_SML    = "SML Scripts"

# VariableCategory enum values
VALID_CATEGORIES = [
    "StatusVariable",
    "DataVariable",
    "Event",
    "Alarm",
    "RemoteCommand",
    "State",
]

# Expected top-level keys in every extraction response
EXTRACTION_RESPONSE_KEYS = {
    "ProjectID", "ExtractionID", "ConfidenceScore", "ExtractionStatus",
    "StatusVariables", "DataVariables", "Events", "Alarms",
    "RemoteCommands", "States", "StateTransitions",
    "Reports", "EventReportLinks", "SmlTemplate",
}

# Sentinel project ID that should never exist on the server
GHOST_PROJECT_ID = 999999999


# ─────────────────────────────────────────────────────────────────────────────
# Minimal synthetic PDF builder (pure stdlib — no dependencies)
# ─────────────────────────────────────────────────────────────────────────────

def _make_minimal_pdf(text: str = "Test document") -> bytes:
    """
    Produce the smallest valid single-page PDF that pypdf can read.
    The text is embedded as a literal string so it can be extracted.
    """
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects = []

    # Object 1 — Catalog
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # Object 2 — Pages
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")

    # Object 3 — Page
    objects.append(
        b"3 0 obj\n"
        b"<< /Type /Page /Parent 2 0 R "
        b"/MediaBox [0 0 612 792] "
        b"/Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>\n"
        b"endobj\n"
    )

    # Object 4 — Content stream
    stream_text = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode()
    stream_obj = (
        f"4 0 obj\n<< /Length {len(stream_text)} >>\nstream\n".encode()
        + stream_text
        + b"\nendstream\nendobj\n"
    )
    objects.append(stream_obj)

    # Object 5 — Font
    objects.append(
        b"5 0 obj\n"
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
        b"endobj\n"
    )

    header = b"%PDF-1.4\n"
    body = b""
    offsets = []
    for obj in objects:
        offsets.append(len(header) + len(body))
        body += obj

    xref_offset = len(header) + len(body)
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n"

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    )

    return header + body + xref.encode() + trailer.encode()


def _make_minimal_xlsx() -> bytes:
    """
    Produce the smallest valid .xlsx file (an Excel Open XML workbook).
    Built entirely from scratch as a ZIP with the minimum required parts.
    """
    def _deflate(data: bytes) -> bytes:
        c = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
        return c.compress(data) + c.flush()

    parts = {
        "[Content_Types].xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            b'<Default Extension="xml" ContentType="application/xml"/>'
            b'<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            b'<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            b'</Types>'
        ),
        "_rels/.rels": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            b'</Relationships>'
        ),
        "xl/workbook.xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
            b' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            b'<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
            b'</workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            b'</Relationships>'
        ),
        "xl/worksheets/sheet1.xml": (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            b'<sheetData>'
            b'<row r="1"><c r="A1" t="inlineStr"><is><t>SVID</t></is></c>'
            b'<c r="B1" t="inlineStr"><is><t>Name</t></is></c></row>'
            b'<row r="2"><c r="A2" t="inlineStr"><is><t>101</t></is></c>'
            b'<c r="B2" t="inlineStr"><is><t>Temperature</t></is></c></row>'
            b'</sheetData>'
            b'</worksheet>'
        ),
    }

    buf = io.BytesIO()
    # Build a minimal ZIP manually
    central_dir = []
    for name_str, data in parts.items():
        name = name_str.encode()
        compressed = _deflate(data)
        crc = zlib.crc32(data) & 0xFFFFFFFF
        offset = buf.tell()

        # Local file header
        buf.write(struct.pack(
            "<4s2H3HL2LHH", b"PK\x03\x04", 20, 0, 8, 0, 0,
            crc, len(compressed), len(data), len(name), 0,
        ))
        buf.write(name)
        buf.write(compressed)

        central_dir.append((name, crc, len(compressed), len(data), offset))

    cd_offset = buf.tell()
    for name, crc, comp_size, uncomp_size, offset in central_dir:
        buf.write(struct.pack(
            "<4s4H3LHHHHHll", b"PK\x01\x02",
            0x0314, 20, 0, 8, 0, 0,
            crc, comp_size, uncomp_size,
            len(name), 0, 0, 0, 0, 0o100644 << 16, offset,
        ))
        buf.write(name)

    cd_size = buf.tell() - cd_offset
    buf.write(struct.pack(
        "<4sHHHHLLH", b"PK\x05\x06",
        0, 0, len(central_dir), len(central_dir),
        cd_size, cd_offset, 0,
    ))
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# TestRunner
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
        symbol = "✅" if condition else "❌"
        suffix = f"  ({detail})" if detail else ""
        print(f"       ↳ {symbol}  {label}{suffix}")
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
        print(f"         Response body: {body[:600]}")

    def summary(self) -> None:
        total = self.passed + self.failed
        status = "ALL PASSED" if self.failed == 0 else f"{self.failed} FAILED"
        print(f"\n{'=' * 60}")
        print(f"  {status}  —  {self.passed}/{total} assertions passed")
        print(f"{'=' * 60}\n")


# ─────────────────────────────────────────────────────────────────────────────
# BaseTestGroup
# ─────────────────────────────────────────────────────────────────────────────

class BaseTestGroup:
    def __init__(
        self,
        runner: TestRunner,
        session: requests.Session,
        base_url: str,
        project_id: int,
        state: dict,
        pdf_bytes: bytes,
    ):
        self.r = runner
        self.s = session
        self.base = base_url.rstrip("/")
        self.project_id = project_id
        self.state = state          # shared mutable dict — groups pass document_id forward
        self.pdf_bytes = pdf_bytes

    def url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def _upload(
        self,
        project_id: int,
        filename: str,
        content: bytes,
        document_type: str = DOC_CATEGORY_GEM,
        content_type: str = "application/pdf",
    ) -> requests.Response:
        files  = {"file": (filename, io.BytesIO(content), content_type)}
        data   = {"document_type": document_type}
        return self.s.post(
            self.url(f"UploadDocument/{project_id}"),
            files=files,
            data=data,
        )

    def run(self):
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Group 1 — POST /UploadDocument/{project_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestUploadDocument(BaseTestGroup):
    """
    Tests
    -----
    1a  Valid PDF upload → 200, response has DocumentID / Status / Pages / FileSize
    1b  Valid .xlsx upload → 200
    1c  Valid .txt upload → 200
    1d  Unsupported file type (.docx) → 400
    1e  Duplicate filename → 409, error mentions conflict
    1f  Upload to nonexistent project → 404
    1g  No file provided (missing multipart field) → 422
    """

    def run(self):
        print("\n── Group 1: POST /UploadDocument/{project_id} ───────────────")

        # ── 1a  Valid PDF ─────────────────────────────────────────────────────

        # REQUEST:  POST /UploadDocument/<project_id>
        #           multipart: file=test_gem_manual.pdf, document_type="GEM Manual"
        response = self._upload(
            self.project_id,
            "test_gem_manual.pdf",
            self.pdf_bytes,
            DOC_CATEGORY_GEM,
        )

        # RESPONSE: status
        ok = self.r.check_status("valid PDF upload → 200", response, 200)
        if ok:
            body = response.json()
            # RESPONSE: body — Status
            self.r.check(
                "Status is 'uploaded'",
                body.get("Status") == "uploaded",
                f"Status='{body.get('Status')}'",
            )
            # RESPONSE: body — DocumentID present and non-empty
            doc_id = body.get("DocumentID", "")
            self.r.check(
                "DocumentID is present and non-empty",
                bool(doc_id),
                f"DocumentID='{doc_id}'",
            )
            # RESPONSE: body — Pages is an integer >= 1
            pages = body.get("Pages", 0)
            self.r.check(
                "Pages is an integer >= 1",
                isinstance(pages, int) and pages >= 1,
                f"Pages={pages}",
            )
            # RESPONSE: body — FileSize is a positive number
            size = body.get("FileSize", 0)
            self.r.check(
                "FileSize is a positive number",
                size > 0,
                f"FileSize={size}",
            )
            # Store document_id for later groups
            self.state["pdf_document_id"] = doc_id

        # ── 1b  Valid .xlsx ───────────────────────────────────────────────────

        # REQUEST:  POST /UploadDocument/<project_id>
        #           multipart: file=test_variables.xlsx, document_type="Variable Files"
        response = self._upload(
            self.project_id,
            "test_variables.xlsx",
            _make_minimal_xlsx(),
            DOC_CATEGORY_VAR,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        # RESPONSE: status
        ok = self.r.check_status("valid .xlsx upload → 200", response, 200)
        if ok:
            body = response.json()
            # RESPONSE: body — Status
            self.r.check(
                "Status is 'uploaded'",
                body.get("Status") == "uploaded",
                f"Status='{body.get('Status')}'",
            )
            self.state["xlsx_document_id"] = body.get("DocumentID", "")

        # ── 1c  Valid .txt ────────────────────────────────────────────────────

        txt_content = b"-- SML script placeholder for automated test --"

        # REQUEST:  POST /UploadDocument/<project_id>
        #           multipart: file=test_script.txt, document_type="SML Scripts"
        response = self._upload(
            self.project_id,
            "test_script.txt",
            txt_content,
            DOC_CATEGORY_SML,
            content_type="text/plain",
        )

        # RESPONSE: status
        ok = self.r.check_status("valid .txt upload → 200", response, 200)
        if ok:
            body = response.json()
            self.r.check(
                "Status is 'uploaded'",
                body.get("Status") == "uploaded",
                f"Status='{body.get('Status')}'",
            )
            self.state["txt_document_id"] = body.get("DocumentID", "")

        # ── 1d  Unsupported file type (.docx) → 400 ──────────────────────────

        dummy_docx = b"PK\x03\x04" + b"\x00" * 26  # fake ZIP header

        # REQUEST:  POST /UploadDocument/<project_id>
        #           multipart: file=unsupported.docx — .docx is not in the accepted list
        response = self._upload(
            self.project_id,
            "unsupported.docx",
            dummy_docx,
            DOC_CATEGORY_USER,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        # RESPONSE: status
        ok = self.r.check_status("unsupported file type (.docx) → 400", response, 400)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions extension or unsupported
            self.r.check(
                "error detail mentions unsupported extension",
                any(kw in detail for kw in ("unsupported", "extension", ".docx", "invalid")),
                f"detail: {detail[:120]}",
            )

        # ── 1e  Duplicate filename → 409 ─────────────────────────────────────

        # REQUEST:  POST /UploadDocument/<project_id>
        #           same filename as 1a (test_gem_manual.pdf) — already uploaded
        response = self._upload(
            self.project_id,
            "test_gem_manual.pdf",
            self.pdf_bytes,
            DOC_CATEGORY_GEM,
        )

        # RESPONSE: status
        ok = self.r.check_status("duplicate filename → 409", response, 409)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions already exists / conflict
            self.r.check(
                "error detail mentions 'already exists' or 'conflict'",
                any(kw in detail for kw in ("already exists", "conflict", "exist")),
                f"detail: {detail[:120]}",
            )

        # ── 1f  Upload to nonexistent project → 404 ──────────────────────────

        # REQUEST:  POST /UploadDocument/999999999 — project does not exist
        response = self._upload(
            GHOST_PROJECT_ID,
            "any_file.pdf",
            self.pdf_bytes,
            DOC_CATEGORY_GEM,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent project → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions project
            self.r.check(
                "error detail mentions 'project' or 'not found'",
                any(kw in detail for kw in ("project", "not found", "found")),
                f"detail: {detail[:120]}",
            )

        # ── 1g  No file field → 422 ───────────────────────────────────────────

        # REQUEST:  POST /UploadDocument/<project_id>
        #           multipart: only document_type, no file field
        response = self.s.post(
            self.url(f"UploadDocument/{self.project_id}"),
            data={"document_type": DOC_CATEGORY_GEM},
        )

        # RESPONSE: status  (FastAPI returns 422 for missing required fields)
        self.r.check_status("missing file field → 422", response, 422)


# ─────────────────────────────────────────────────────────────────────────────
# Group 2 — GET /Analyze/{project_id}/{document_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzeDocument(BaseTestGroup):
    """
    Tests
    -----
    2a  Valid project + document → 200, all extraction response keys present,
        ExtractionStatus is 'completed' or 'failed' (LLM may fail on tiny PDF),
        SmlTemplate is present
    2b  Nonexistent document_id → 404
    2c  Nonexistent project → 404

    NOTE: This group triggers the LLM. Allow 30–90 seconds.
    """

    def run(self):
        print("\n── Group 2: GET /Analyze/{project_id}/{document_id} ─────────")
        print("     ⏳  Triggering LLM extraction — this may take 30–90 seconds …")

        doc_id = self.state.get("pdf_document_id", "")
        if not doc_id:
            print("     ⚠️  No PDF document_id from Group 1 — skipping Group 2.")
            return

        # ── 2a  Valid analyze ─────────────────────────────────────────────────

        # REQUEST:  GET /Analyze/<project_id>/<document_id>
        response = self.s.get(
            self.url(f"Analyze/{self.project_id}/{doc_id}"),
            timeout=180,
        )

        # RESPONSE: status
        ok = self.r.check_status("valid analyze call → 200", response, 200)
        if ok:
            body = response.json()

            # RESPONSE: body — all required top-level keys present
            missing_keys = EXTRACTION_RESPONSE_KEYS - body.keys()
            self.r.check(
                "all required extraction keys present in response",
                not missing_keys,
                f"missing: {missing_keys}" if missing_keys else "",
            )

            # RESPONSE: body — ExtractionStatus is a known value
            status = body.get("ExtractionStatus", "")
            self.r.check(
                "ExtractionStatus is 'completed' or 'failed'",
                status in ("completed", "failed"),
                f"ExtractionStatus='{status}'",
            )

            # RESPONSE: body — ConfidenceScore is a float in [0.0, 1.0]
            score = body.get("ConfidenceScore", -1)
            self.r.check(
                "ConfidenceScore is a float between 0.0 and 1.0",
                isinstance(score, (int, float)) and 0.0 <= score <= 1.0,
                f"ConfidenceScore={score}",
            )

            # RESPONSE: body — SmlTemplate is present and non-empty
            sml = body.get("SmlTemplate")
            self.r.check(
                "SmlTemplate is present and non-empty",
                bool(sml),
                "SmlTemplate present" if sml else "SmlTemplate missing or empty",
            )

            # RESPONSE: body — ProjectID matches
            self.r.check(
                "ProjectID in response matches the request",
                body.get("ProjectID") == self.project_id,
                f"got ProjectID={body.get('ProjectID')}",
            )

            # Mark as completed in shared state so later groups can use it
            self.state["analysis_status"] = status

        # ── 2b  Nonexistent document → 404 ───────────────────────────────────

        # REQUEST:  GET /Analyze/<project_id>/ghost_doc_xyzzy
        response = self.s.get(
            self.url(f"Analyze/{self.project_id}/ghost_doc_xyzzy"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent document_id → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions document / not found
            self.r.check(
                "error detail mentions 'document' or 'not found'",
                any(kw in detail for kw in ("document", "not found", "found")),
                f"detail: {detail[:120]}",
            )

        # ── 2c  Nonexistent project → 404 ────────────────────────────────────

        # REQUEST:  GET /Analyze/999999999/<document_id>
        response = self.s.get(
            self.url(f"Analyze/{GHOST_PROJECT_ID}/{doc_id}"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent project → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            self.r.check(
                "error detail mentions 'project' or 'not found'",
                any(kw in detail for kw in ("project", "not found", "found")),
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 3 — GET /AnalyzeProject/{project_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyzeProject(BaseTestGroup):
    """
    Tests
    -----
    3a  Valid project → 200, aggregated response has all extraction keys
    3b  Nonexistent project → 404
    """

    def run(self):
        print("\n── Group 3: GET /AnalyzeProject/{project_id} ────────────────")
        print("     ⏳  Running AnalyzeProject — may be slow if documents are pending …")

        # ── 3a  Valid project ─────────────────────────────────────────────────

        # REQUEST:  GET /AnalyzeProject/<project_id>
        response = self.s.get(
            self.url(f"AnalyzeProject/{self.project_id}"),
            timeout=180,
        )

        # RESPONSE: status
        ok = self.r.check_status("valid AnalyzeProject → 200", response, 200)
        if ok:
            body = response.json()

            # RESPONSE: body — all required top-level keys
            missing_keys = EXTRACTION_RESPONSE_KEYS - body.keys()
            self.r.check(
                "all required extraction keys present",
                not missing_keys,
                f"missing: {missing_keys}" if missing_keys else "",
            )

            # RESPONSE: body — ExtractionStatus
            status = body.get("ExtractionStatus", "")
            self.r.check(
                "ExtractionStatus is 'completed' or 'failed'",
                status in ("completed", "failed"),
                f"ExtractionStatus='{status}'",
            )

            # RESPONSE: body — ExtractionID is 'project_batch'
            self.r.check(
                "ExtractionID is 'project_batch'",
                body.get("ExtractionID") == "project_batch",
                f"ExtractionID='{body.get('ExtractionID')}'",
            )

        # ── 3b  Nonexistent project → 404 ────────────────────────────────────

        # REQUEST:  GET /AnalyzeProject/999999999
        response = self.s.get(
            self.url(f"AnalyzeProject/{GHOST_PROJECT_ID}"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent project → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            self.r.check(
                "error detail mentions 'project' or 'not found'",
                any(kw in detail for kw in ("project", "not found", "found")),
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 4 — GET /Analyze/{project_id}/{document_id}/report
# ─────────────────────────────────────────────────────────────────────────────

class TestDownloadReport(BaseTestGroup):
    """
    Tests
    -----
    4a  Completed document → 200, Content-Disposition header present,
        response body is valid JSON with expected keys
    4b  Nonexistent document → 404
    4c  Nonexistent project → 404
    """

    def run(self):
        print("\n── Group 4: GET /Analyze/{project_id}/{document_id}/report ──")

        doc_id = self.state.get("pdf_document_id", "")
        if not doc_id:
            print("     ⚠️  No PDF document_id from Group 1 — skipping Group 4.")
            return

        # ── 4a  Valid download ────────────────────────────────────────────────

        # REQUEST:  GET /Analyze/<project_id>/<document_id>/report
        response = self.s.get(
            self.url(f"Analyze/{self.project_id}/{doc_id}/report"),
            timeout=30,
        )

        # RESPONSE: status
        ok = self.r.check_status("download report for completed doc → 200", response, 200)
        if ok:
            # RESPONSE: headers — Content-Disposition must be set
            cd = response.headers.get("Content-Disposition", "")
            self.r.check(
                "Content-Disposition header is present",
                bool(cd),
                f"Content-Disposition='{cd}'",
            )
            # RESPONSE: headers — filename contains document_id
            self.r.check(
                "Content-Disposition filename contains document_id",
                doc_id in cd,
                f"Content-Disposition='{cd}'",
            )
            # RESPONSE: body — parseable as JSON
            try:
                report_json = response.json()
                is_json = True
            except Exception:
                report_json = {}
                is_json = False
            self.r.check("response body is valid JSON", is_json)

            if is_json:
                # RESPONSE: body — has at least ToolID or StatusVariables
                self.r.check(
                    "JSON body contains 'ToolID' or 'StatusVariables'",
                    any(k in report_json for k in ("ToolID", "StatusVariables", "tool_id")),
                    f"keys found: {list(report_json.keys())[:8]}",
                )

        # ── 4b  Nonexistent document → 404 ───────────────────────────────────

        # REQUEST:  GET /Analyze/<project_id>/ghost_doc_xyzzy/report
        response = self.s.get(
            self.url(f"Analyze/{self.project_id}/ghost_doc_xyzzy/report"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent document → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            self.r.check(
                "error detail mentions 'document' or 'not found'",
                any(kw in detail for kw in ("document", "not found", "found")),
                f"detail: {detail[:120]}",
            )

        # ── 4c  Nonexistent project → 404 ────────────────────────────────────

        # REQUEST:  GET /Analyze/999999999/<document_id>/report
        response = self.s.get(
            self.url(f"Analyze/{GHOST_PROJECT_ID}/{doc_id}/report"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent project → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            self.r.check(
                "error detail mentions 'project' or 'not found'",
                any(kw in detail for kw in ("project", "not found", "found")),
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 5 — GET /GetVariable/{project_id}/{document_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestGetVariable(BaseTestGroup):
    """
    Tests
    -----
    5a  No categories param → 200, Categories list and Results present
    5b  Single valid category (StatusVariable) → 200, only that key in Results
    5c  Multiple valid categories (StatusVariable,Event) → 200, both in Results
    5d  Invalid category value → 400, error mentions the bad value
    5e  Document not yet analyzed (xlsx doc is still 'uploaded') → 400
    5f  Nonexistent document → 404
    5g  Nonexistent project → 404

    NOTE: Tests 5a–5c only make assertions about structure, not data content,
    because the LLM extraction on a tiny synthetic PDF may return empty lists.
    """

    def run(self):
        print("\n── Group 5: GET /GetVariable/{project_id}/{document_id} ─────")

        doc_id = self.state.get("pdf_document_id", "")
        if not doc_id:
            print("     ⚠️  No PDF document_id from Group 1 — skipping Group 5.")
            return

        analysis_status = self.state.get("analysis_status", "unknown")
        if analysis_status != "completed":
            print(f"     ⚠️  Analysis status='{analysis_status}'. "
                  "GetVariable tests on completed doc may return 400 — running anyway.")

        # ── 5a  No categories param → all categories ──────────────────────────

        # REQUEST:  GET /GetVariable/<project_id>/<document_id>
        #           no query params
        response = self.s.get(
            self.url(f"GetVariable/{self.project_id}/{doc_id}"),
            timeout=15,
        )

        # RESPONSE: status  (400 if extraction was empty / not completed)
        ok = self.r.check_status(
            "no categories param → 200 (requires completed extraction)", response, 200
        )
        if ok:
            body = response.json()
            # RESPONSE: body — Categories key present
            self.r.check(
                "response has 'Categories' key",
                "Categories" in body,
                f"keys: {list(body.keys())}",
            )
            # RESPONSE: body — TotalCount is a non-negative integer
            total = body.get("TotalCount", -1)
            self.r.check(
                "TotalCount is a non-negative integer",
                isinstance(total, int) and total >= 0,
                f"TotalCount={total}",
            )
            # RESPONSE: body — Results key present
            self.r.check(
                "response has 'Results' key",
                "Results" in body,
                f"keys: {list(body.keys())}",
            )

        # ── 5b  Single valid category ─────────────────────────────────────────

        # REQUEST:  GET /GetVariable/<project_id>/<document_id>?categories=StatusVariable
        response = self.s.get(
            self.url(f"GetVariable/{self.project_id}/{doc_id}"),
            params={"categories": "StatusVariable"},
            timeout=15,
        )

        # RESPONSE: status
        ok = self.r.check_status(
            "categories=StatusVariable → 200 (if data exists)", response, 200
        )
        if ok:
            body = response.json()
            results = body.get("Results", {})
            # RESPONSE: body — only StatusVariable category in results
            unexpected = [k for k in results if k != "StatusVariable"]
            self.r.check(
                "Results contains only 'StatusVariable'",
                not unexpected,
                f"unexpected keys: {unexpected}" if unexpected else "",
            )

        # ── 5c  Multiple valid categories ────────────────────────────────────

        # REQUEST:  GET /GetVariable/<project_id>/<document_id>?categories=StatusVariable,Event
        response = self.s.get(
            self.url(f"GetVariable/{self.project_id}/{doc_id}"),
            params={"categories": "StatusVariable,Event"},
            timeout=15,
        )

        # RESPONSE: status (200 if at least one category has data)
        ok = self.r.check_status(
            "categories=StatusVariable,Event → 200 (if data exists)", response, 200
        )
        if ok:
            body = response.json()
            results = body.get("Results", {})
            # RESPONSE: body — no keys outside the requested two
            unexpected = [k for k in results if k not in ("StatusVariable", "Event")]
            self.r.check(
                "Results contains only 'StatusVariable' and/or 'Event'",
                not unexpected,
                f"unexpected keys: {unexpected}" if unexpected else "",
            )

        # ── 5d  Invalid category value → 400 ─────────────────────────────────

        # REQUEST:  GET /GetVariable/<project_id>/<document_id>?categories=NotARealCategory
        response = self.s.get(
            self.url(f"GetVariable/{self.project_id}/{doc_id}"),
            params={"categories": "NotARealCategory"},
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("invalid category value → 400", response, 400)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions the bad value or "invalid"
            self.r.check(
                "error detail mentions invalid value or category",
                any(kw in detail for kw in ("invalid", "notarealcategory", "valid values", "category")),
                f"detail: {detail[:120]}",
            )

        # ── 5e  Document not yet completed (xlsx still 'uploaded') → 400 ─────
        xlsx_id = self.state.get("xlsx_document_id", "")
        if xlsx_id:
            # REQUEST:  GET /GetVariable/<project_id>/<xlsx_document_id>
            #           xlsx was uploaded but never analyzed
            response = self.s.get(
                self.url(f"GetVariable/{self.project_id}/{xlsx_id}"),
                timeout=10,
            )

            # RESPONSE: status  (400 because status != 'completed')
            ok = self.r.check_status(
                "not-yet-analyzed document → 400", response, 400
            )
            if ok:
                detail = str(response.json()).lower()
                # RESPONSE: body — error mentions extraction / completed
                self.r.check(
                    "error detail mentions extraction not completed",
                    any(kw in detail for kw in ("completed", "extraction", "not")),
                    f"detail: {detail[:120]}",
                )

        # ── 5f  Nonexistent document → 404 ───────────────────────────────────

        # REQUEST:  GET /GetVariable/<project_id>/ghost_doc_xyzzy
        response = self.s.get(
            self.url(f"GetVariable/{self.project_id}/ghost_doc_xyzzy"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent document → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            self.r.check(
                "error detail mentions 'document' or 'not found'",
                any(kw in detail for kw in ("document", "not found", "found")),
                f"detail: {detail[:120]}",
            )

        # ── 5g  Nonexistent project → 404 ────────────────────────────────────

        # REQUEST:  GET /GetVariable/999999999/<document_id>
        response = self.s.get(
            self.url(f"GetVariable/{GHOST_PROJECT_ID}/{doc_id}"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent project → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            self.r.check(
                "error detail mentions 'project' or 'not found'",
                any(kw in detail for kw in ("project", "not found", "found")),
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 6 — DELETE /DeleteDocument/{project_id}/{document_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteDocument(BaseTestGroup):
    """
    Tests
    -----
    6a  Valid delete of the xlsx doc → 200, Status=success, Message present
    6b  Delete again (already gone) → 404
    6c  Delete from nonexistent project → 404
    """

    def run(self):
        print("\n── Group 6: DELETE /DeleteDocument/{project_id}/{document_id}")

        xlsx_id = self.state.get("xlsx_document_id", "")
        if not xlsx_id:
            print("     ⚠️  No xlsx document_id from Group 1 — skipping Group 6.")
            return

        # ── 6a  Valid delete ──────────────────────────────────────────────────

        # REQUEST:  DELETE /DeleteDocument/<project_id>/<xlsx_document_id>
        response = self.s.delete(
            self.url(f"DeleteDocument/{self.project_id}/{xlsx_id}"),
            timeout=15,
        )

        # RESPONSE: status
        ok = self.r.check_status("valid delete → 200", response, 200)
        if ok:
            body = response.json()
            # RESPONSE: body — Status is 'success'
            self.r.check(
                "Status is 'success'",
                body.get("Status") == "success",
                f"Status='{body.get('Status')}'",
            )
            # RESPONSE: body — Message is present
            self.r.check(
                "Message field is present",
                bool(body.get("Message")),
                f"Message='{body.get('Message', '')}'",
            )

        # ── 6b  Delete again → 404 ────────────────────────────────────────────

        # REQUEST:  DELETE /DeleteDocument/<project_id>/<xlsx_document_id>
        #           document was just deleted in 6a — should no longer exist
        response = self.s.delete(
            self.url(f"DeleteDocument/{self.project_id}/{xlsx_id}"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("delete already-deleted document → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions not found
            self.r.check(
                "error detail mentions 'not found' or 'document'",
                any(kw in detail for kw in ("not found", "document", "found")),
                f"detail: {detail[:120]}",
            )

        # ── 6c  Delete from nonexistent project → 404 ────────────────────────

        # REQUEST:  DELETE /DeleteDocument/999999999/<xlsx_document_id>
        response = self.s.delete(
            self.url(f"DeleteDocument/{GHOST_PROJECT_ID}/{xlsx_id}"),
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("delete from nonexistent project → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            self.r.check(
                "error detail mentions 'project' or 'not found'",
                any(kw in detail for kw in ("project", "not found", "found")),
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# Group 7 — POST /UpdateExtraction/{project_id}
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateExtraction(BaseTestGroup):
    """
    Tests
    -----
    7a  Valid minimal EquipmentSpec body → 200, Status=success
    7b  Nonexistent project → 404
    """

    # Minimal valid EquipmentSpec payload (matches source/schemas/secsgem.py)
    _MINIMAL_SPEC = {
        "ToolID": "TEST-TOOL-001",
        "ToolType": "CVD",
        "Protocol": "SECS/GEM",
        "StatusVariable": [],
        "DataVariable": [],
        "events": [],
        "alarms": [],
        "remote_commands": [],
        "states": [],
        "state_transitions": [],
        "reports": [],
        "event_report_links": [],
    }

    def run(self):
        print("\n── Group 7: POST /UpdateExtraction/{project_id} ─────────────")

        # ── 7a  Valid update ──────────────────────────────────────────────────

        # REQUEST:  POST /UpdateExtraction/<project_id>
        #           JSON body: minimal valid EquipmentSpec
        response = self.s.post(
            self.url(f"UpdateExtraction/{self.project_id}"),
            json=self._MINIMAL_SPEC,
            timeout=15,
        )

        # RESPONSE: status
        ok = self.r.check_status("valid EquipmentSpec body → 200", response, 200)
        if ok:
            body = response.json()
            # RESPONSE: body — Status is 'success'
            self.r.check(
                "Status is 'success'",
                body.get("Status") == "success",
                f"Status='{body.get('Status')}'",
            )
            # RESPONSE: body — Message is present
            self.r.check(
                "Message field is present",
                bool(body.get("Message")),
                f"Message='{body.get('Message', '')}'",
            )

        # ── 7b  Nonexistent project → 404 ────────────────────────────────────

        # REQUEST:  POST /UpdateExtraction/999999999
        response = self.s.post(
            self.url(f"UpdateExtraction/{GHOST_PROJECT_ID}"),
            json=self._MINIMAL_SPEC,
            timeout=10,
        )

        # RESPONSE: status
        ok = self.r.check_status("nonexistent project → 404", response, 404)
        if ok:
            detail = str(response.json()).lower()
            # RESPONSE: body — error mentions project
            self.r.check(
                "error detail mentions 'project' or 'not found'",
                any(kw in detail for kw in ("project", "not found", "found")),
                f"detail: {detail[:120]}",
            )


# ─────────────────────────────────────────────────────────────────────────────
# DocumentsTestSuite  —  orchestrates setup, all groups, teardown
# ─────────────────────────────────────────────────────────────────────────────

class DocumentsTestSuite:
    def __init__(
        self,
        base_url: str = BASE_URL,
        verbose: bool = False,
        pdf_path: str = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.runner = TestRunner(verbose=verbose)
        self.session = requests.Session()
        self.pdf_path = pdf_path
        self.project_id: int = None
        self.state: dict = {}           # shared across groups

    # ── Server health check ───────────────────────────────────────────────────

    def _check_server(self) -> None:
        try:
            r = self.session.get(f"{self.base_url}/health", timeout=5)
            r.raise_for_status()
        except Exception as e:
            print(f"\n❌  Cannot reach server at {self.base_url}: {e}")
            sys.exit(1)

    # ── PDF loading ───────────────────────────────────────────────────────────

    def _load_pdf(self) -> bytes:
        if self.pdf_path:
            with open(self.pdf_path, "rb") as f:
                data = f.read()
            print(f"  📄  Using PDF: {self.pdf_path} ({len(data):,} bytes)")
            return data
        else:
            data = _make_minimal_pdf(
                "SECS/GEM Equipment Interface Spec\n"
                "Status Variable SVID 101 ChamberTemperature Float\n"
                "Collection Event CEID 201 ProcessStart\n"
                "Alarm AlarmID 301 HighTemperature Critical\n"
            )
            print(f"  📄  No --pdf supplied. Using synthetic minimal PDF ({len(data):,} bytes).")
            print("      For richer extraction tests, pass a real GEM manual with --pdf.")
            return data

    # ── Suite-level project setup / teardown ──────────────────────────────────

    def _setup(self) -> None:
        print("\n── Suite Setup: creating temporary test project ─────────────")
        payload = {
            "ProjectName": "AutoTest_Documents_Project",
            "VendorName":  "TestVendor",
            "ProjectCode": "AUTOTEST-DOC-001",
            "Tool":        "CVD",
        }

        # REQUEST:  POST /AddProject
        r = self.session.post(f"{self.base_url}/AddProject", json=payload, timeout=15)

        if r.status_code not in (200, 201):
            print(f"  ❌  Failed to create test project: {r.status_code} {r.text[:200]}")
            sys.exit(1)

        self.project_id = r.json().get("ProjectID")
        print(f"  ✅  Test project created — ProjectID={self.project_id}")

    def _teardown(self) -> None:
        print("\n── Suite Teardown: deleting temporary test project ──────────")
        if not self.project_id:
            print("  ⚠️  No project_id to clean up.")
            return

        # REQUEST:  DELETE /DeleteProject/<project_id>
        r = self.session.delete(
            f"{self.base_url}/DeleteProject/{self.project_id}", timeout=15
        )
        if r.status_code == 200:
            print(f"  ✅  Project {self.project_id} deleted successfully.")
        else:
            print(
                f"  ⚠️  Could not delete project {self.project_id}: "
                f"{r.status_code} {r.text[:120]}"
            )
            print("      Please delete it manually to keep the server clean.")

    # ── Main run ──────────────────────────────────────────────────────────────

    def run(self) -> None:
        print(f"\n{'=' * 60}")
        print(f"  Documents API  —  Test Suite")
        print(f"  Target : {self.base_url}")
        print(f"{'=' * 60}")

        self._check_server()
        pdf_bytes = self._load_pdf()
        self._setup()

        group_kwargs = dict(
            runner=self.runner,
            session=self.session,
            base_url=self.base_url,
            project_id=self.project_id,
            state=self.state,
            pdf_bytes=pdf_bytes,
        )

        groups = [
            TestUploadDocument,
            TestAnalyzeDocument,
            TestAnalyzeProject,
            TestDownloadReport,
            TestGetVariable,
            TestDeleteDocument,
            TestUpdateExtraction,
        ]

        for GroupClass in groups:
            GroupClass(**group_kwargs).run()

        self._teardown()
        self.runner.summary()
        sys.exit(0 if self.runner.failed == 0 else 1)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Documents API test suite")
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
    parser.add_argument(
        "--pdf",
        default=None,
        metavar="PATH",
        help="Path to a real PDF to upload (recommended for richer extraction tests)",
    )
    args = parser.parse_args()

    DocumentsTestSuite(
        base_url=args.url,
        verbose=args.verbose,
        pdf_path=args.pdf,
    ).run()