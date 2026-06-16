import pytest
from fastapi.testclient import TestClient

def test_update_reports_not_found(client: TestClient, record_property):
    """Test updating reports on a non-existent project (HTTP 400 or 404)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateReports/{project_id}")
    
    payload = {"Reports": []}
    response = client.put("/UpdateReports/99999", json=payload)
    # The endpoint's try-except catches all exceptions and raises 400
    assert response.status_code in (400, 404)

def test_update_reports_happy_path(client: TestClient, record_property):
    """Test updating reports successfully on an existing project (Happy Path)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateReports/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "UpReportProj", "VendorName": "V", "ProjectCode": "UR1"})
    pid = p.json().get("ProjectID")
    
    try:
        payload = {
            "Reports": [
                {
                    "RPTID": 101,
                    "Name": "StatusReport",
                    "LinkedVIDs": [1, 2],
                    "Reasoning": "Report of basic variables",
                    "Type": "Event",
                    "Confidence": 0.95
                }
            ]
        }
        response = client.put(f"/UpdateReports/{pid}", json=payload)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
    finally:
        client.delete(f"/DeleteProject/{pid}")
