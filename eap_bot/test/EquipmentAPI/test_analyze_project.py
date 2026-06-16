import pytest
from fastapi.testclient import TestClient

def test_analyze_project_happy_path(client: TestClient, record_property):
    """Test analyzing a project (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/AnalyzeProject/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "AnalyzeProjTest", "VendorName": "V", "ProjectCode": "AP1"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.get(f"/AnalyzeProject/{pid}")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        # Verify extraction response format
        assert "project_id" in data or "ProjectID" in data or "StatusVariables" in data
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_analyze_project_not_found(client: TestClient, record_property):
    """Test analyzing a project that does not exist (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/AnalyzeProject/{project_id}")
    
    response = client.get("/AnalyzeProject/99999")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
