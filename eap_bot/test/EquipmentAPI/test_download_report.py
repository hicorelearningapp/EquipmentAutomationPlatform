import pytest
from fastapi.testclient import TestClient

def test_download_report_not_found(client: TestClient, record_property):
    """Test downloading report for non-existent document or project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/Analyze/{project_id}/{document_id}/report")
    
    p = client.post("/CreateProject", json={"ProjectName": "ReportFailProj", "VendorName": "V", "ProjectCode": "R1"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.get(f"/Analyze/{pid}/non_existent_doc/report")
        record_property("expected", 404)
        record_property("got", response.status_code)
        assert response.status_code == 404
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_download_report_project_not_found(client: TestClient, record_property):
    """Test downloading report on a non-existent project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/Analyze/{project_id}/{document_id}/report")
    
    response = client.get("/Analyze/99999/some_doc/report")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
