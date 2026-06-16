import pytest
from fastapi.testclient import TestClient

def test_get_project_details_happy_path(client: TestClient, record_property):
    """Test retrieving details of an existing project (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/GetProjectDetails/{project_id}")
    
    # Create project
    p = client.post("/CreateProject", json={"ProjectName": "DetailsProjTest", "VendorName": "V", "ProjectCode": "D1", "Tool": "CVD"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.get(f"/GetProjectDetails/{pid}")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("Id") == pid
        assert data.get("ProjectName") == "DetailsProjTest"
        assert data.get("ProjectCode") == "D1"
        assert data.get("Tool") == "CVD"
        assert "DocumentCount" in data
        assert "SVCount" in data
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_get_project_details_not_found(client: TestClient, record_property):
    """Test retrieving details for non-existent project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetProjectDetails/{project_id}")
    
    response = client.get("/GetProjectDetails/99999")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_get_project_details_invalid_id(client: TestClient, record_property):
    """Test parameter validation failure (HTTP 422)."""
    record_property("method", "GET")
    record_property("url", "/GetProjectDetails/{project_id}")
    
    response = client.get("/GetProjectDetails/abc")
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422
