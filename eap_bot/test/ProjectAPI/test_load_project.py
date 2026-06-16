import pytest
from fastapi.testclient import TestClient

def test_load_project_happy_path(client: TestClient, record_property):
    """Test loading an existing project successfully (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/LoadProject/{project_id}")
    
    # Create a test project first
    payload = {
        "ProjectName": "LoadProjectSuccess",
        "VendorName": "VendorLoad",
        "ProjectCode": "LP-01",
        "Tool": "CVD"
    }
    create_response = client.post("/CreateProject", json=payload)
    assert create_response.status_code == 201
    project_id = create_response.json().get("ProjectID")
    
    try:
        # Load the project
        response = client.get(f"/LoadProject/{project_id}")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("ProjectID") == project_id
        assert data.get("ProjectName") == "LoadProjectSuccess"
        assert "Extractions" in data
        assert "Mappings" in data
        assert "SmlTemplate" in data
        assert "Questions" in data
    finally:
        # Cleanup
        client.delete(f"/DeleteProject/{project_id}")

def test_load_project_not_found(client: TestClient, record_property):
    """Test loading a project that does not exist (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/LoadProject/{project_id}")
    
    non_existent_id = 99999
    response = client.get(f"/LoadProject/{non_existent_id}")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
    assert "not found" in response.json().get("detail", "").lower()

def test_load_project_invalid_id_type(client: TestClient, record_property):
    """Test validation failure when project_id is not an integer (HTTP 422)."""
    record_property("method", "GET")
    record_property("url", "/LoadProject/{project_id}")
    
    response = client.get("/LoadProject/abc")
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422
    assert "integer" in response.json().get("detail", "")[0].get("msg", "").lower()
