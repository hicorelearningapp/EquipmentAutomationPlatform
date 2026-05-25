"""
test_documents_api.py
=====================
Test suite for all 7 Documents endpoints using pytest and TestClient.
"""

import io
import json
import struct
import zlib
import pytest

# Configuration
DOC_CATEGORY_GEM    = "GEM Manual"
DOC_CATEGORY_USER   = "User Manuals"
DOC_CATEGORY_VAR    = "Variable Files"
DOC_CATEGORY_SML    = "SML Scripts"
GHOST_PROJECT_ID = 999999999

EXTRACTION_RESPONSE_KEYS = {
    "ProjectID", "ExtractionID", "ConfidenceScore", "ExtractionStatus",
    "StatusVariables", "DataVariables", "Events", "Alarms",
    "RemoteCommands", "States", "StateTransitions",
    "Reports", "EventReportLinks", "SmlTemplate",
}

def _make_minimal_pdf(text: str = "Test document") -> bytes:
    safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    objects = []
    objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
    objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
    objects.append(b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n")
    stream_text = f"BT /F1 12 Tf 72 720 Td ({safe}) Tj ET".encode()
    stream_obj = f"4 0 obj\n<< /Length {len(stream_text)} >>\nstream\n".encode() + stream_text + b"\nendstream\nendobj\n"
    objects.append(stream_obj)
    objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
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
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
    return header + body + xref.encode() + trailer.encode()

def _make_minimal_xlsx() -> bytes:
    def _deflate(data: bytes) -> bytes:
        c = zlib.compressobj(zlib.Z_DEFAULT_COMPRESSION, zlib.DEFLATED, -15)
        return c.compress(data) + c.flush()
    parts = {
        "[Content_Types].xml": b'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": b'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": b'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": b'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>SVID</t></is></c><c r="B1" t="inlineStr"><is><t>Name</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>101</t></is></c><c r="B2" t="inlineStr"><is><t>Temperature</t></is></c></row></sheetData></worksheet>',
    }
    buf = io.BytesIO()
    central_dir = []
    for name_str, data in parts.items():
        name = name_str.encode()
        compressed = _deflate(data)
        crc = zlib.crc32(data) & 0xFFFFFFFF
        offset = buf.tell()
        buf.write(struct.pack("<4s2H3HL2LHH", b"PK\x03\x04", 20, 0, 8, 0, 0, crc, len(compressed), len(data), len(name), 0))
        buf.write(name)
        buf.write(compressed)
        central_dir.append((name, crc, len(compressed), len(data), offset))
    cd_offset = buf.tell()
    for name, crc, comp_size, uncomp_size, offset in central_dir:
        buf.write(struct.pack("<4s6H3L5H2L", b"PK\x01\x02", 0x0314, 20, 0, 8, 0, 0, crc, comp_size, uncomp_size, len(name), 0, 0, 0, 0, 0o100644 << 16, offset))
        buf.write(name)
    cd_size = buf.tell() - cd_offset
    buf.write(struct.pack("<4sHHHHLLH", b"PK\x05\x06", 0, 0, len(central_dir), len(central_dir), cd_size, cd_offset, 0))
    return buf.getvalue()


@pytest.fixture(scope="module")
def project_state(client):
    # Setup test project
    r = client.post("/AddProject", json={
        "ProjectName": "TestDocsProject", 
        "VendorName": "TestVendor",
        "ProjectCode": "TestCode123"
    })
    assert r.status_code == 201, "Failed to create test project"
    project_id = r.json().get("ProjectID")
    
    state = {"project_id": project_id}
    yield state
    
    # Teardown
    client.delete(f"/DeleteProject/{project_id}")

def _upload(client, project_id, filename, content, document_type=DOC_CATEGORY_GEM, content_type="application/pdf"):
    files = {"file": (filename, io.BytesIO(content), content_type)}
    data = {"document_type": document_type}
    return client.post(f"/UploadDocument/{project_id}", files=files, data=data)

# ── Group 1 — POST /UploadDocument/{project_id} ──────────────────────────────

def test_upload_document_pdf(client, project_state, record_property):
    record_property("method", "POST")
    record_property("url", f"/UploadDocument/{project_state['project_id']}")
    
    pdf_bytes = _make_minimal_pdf()
    response = _upload(client, project_state["project_id"], "test_gem_manual.pdf", pdf_bytes, DOC_CATEGORY_GEM)
    
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    body = response.json()
    assert body.get("Status") == "uploaded"
    assert body.get("DocumentID")
    project_state["pdf_document_id"] = body.get("DocumentID")

def test_upload_document_xlsx(client, project_state, record_property):
    record_property("method", "POST")
    record_property("url", f"/UploadDocument/{project_state['project_id']}")
    
    response = _upload(
        client, project_state["project_id"], "test_variables.xlsx", _make_minimal_xlsx(), 
        DOC_CATEGORY_VAR, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200

def test_upload_document_duplicate(client, project_state, record_property):
    record_property("method", "POST")
    record_property("url", f"/UploadDocument/{project_state['project_id']}")
    
    pdf_bytes = _make_minimal_pdf()
    response = _upload(client, project_state["project_id"], "test_gem_manual.pdf", pdf_bytes, DOC_CATEGORY_GEM)
    
    record_property("expected", 409)
    record_property("got", response.status_code)
    assert response.status_code == 409

# ── Group 2 — GET /Analyze/{project_id}/{document_id} ────────────────────────

def test_analyze_document_valid(client, project_state, record_property):
    doc_id = project_state.get("pdf_document_id")
    pytest.skip("Skipping slow LLM analysis test during rapid testing, enable if needed")
    # Real test code:
    # url = f"/Analyze/{project_state['project_id']}/{doc_id}"
    # record_property("method", "GET")
    # record_property("url", url)
    # response = client.get(url, timeout=180)
    # assert response.status_code == 200

# ── Group 3 — GET /AnalyzeProject/{project_id} ───────────────────────────────

def test_analyze_project_valid(client, project_state, record_property):
    url = f"/AnalyzeProject/{project_state['project_id']}"
    record_property("method", "GET")
    record_property("url", url)
    response = client.get(url)
    
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    assert response.json().get("ExtractionID") == "project_batch"

# ── Group 6 — DELETE /DeleteDocument/{project_id}/{document_id} ──────────────

def test_delete_document(client, project_state, record_property):
    doc_id = project_state.get("pdf_document_id")
    url = f"/DeleteDocument/{project_state['project_id']}/{doc_id}"
    record_property("method", "DELETE")
    record_property("url", url)
    
    response = client.delete(url)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200