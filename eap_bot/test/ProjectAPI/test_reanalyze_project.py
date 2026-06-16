import pytest
from fastapi.testclient import TestClient

def test_reanalyze_project_happy_path(client: TestClient, record_property):
    """Test re-analyzing an existing project successfully (Happy Path)."""
    record_property("method", "POST")
    record_property("url", "/ReAnalyzeProject/{project_id}")
    
    # Create a test project
    payload = {
        "ProjectName": "ReAnalyzeSuccess",
        "VendorName": "VendorRe",
        "ProjectCode": "RAP-01",
        "Tool": "CVD"
    }
    create_response = client.post("/CreateProject", json=payload)
    assert create_response.status_code == 201
    project_id = create_response.json().get("ProjectID")
    
    try:
        # Trigger re-analysis
        response = client.post(f"/ReAnalyzeProject/{project_id}")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("ProjectID") == project_id
        assert data.get("ProjectName") == "ReAnalyzeSuccess"
        assert "Extractions" in data
        assert "Mappings" in data
        assert "SmlTemplate" in data
    finally:
        client.delete(f"/DeleteProject/{project_id}")

def test_reanalyze_project_not_found(client: TestClient, record_property):
    """Test re-analyzing a project that does not exist (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/ReAnalyzeProject/{project_id}")
    
    non_existent_id = 99999
    response = client.post(f"/ReAnalyzeProject/{non_existent_id}")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_reanalyze_project_invalid_id_type(client: TestClient, record_property):
    """Test validation failure when project_id is not an integer (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/ReAnalyzeProject/{project_id}")
    
    response = client.post("/ReAnalyzeProject/abc")
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422
