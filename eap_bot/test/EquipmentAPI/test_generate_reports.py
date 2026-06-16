import pytest
from fastapi.testclient import TestClient

def test_generate_reports_not_found(client: TestClient, record_property):
    """Test generating reports on a non-existent project (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/GenerateReports/{project_id}")
    
    payload = {"ceids": []}
    response = client.post("/GenerateReports/99999", json=payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_generate_reports_happy_path(client: TestClient, record_property):
    """Test generating reports for an existing project (Happy Path)."""
    record_property("method", "POST")
    record_property("url", "/GenerateReports/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "GenReportProj", "VendorName": "V", "ProjectCode": "GR1"})
    pid = p.json().get("ProjectID")
    
    try:
        payload = {"ceids": []}
        response = client.post(f"/GenerateReports/{pid}", json=payload)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
    finally:
        client.delete(f"/DeleteProject/{pid}")
