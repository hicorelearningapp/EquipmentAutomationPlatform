import pytest
from fastapi.testclient import TestClient

def test_delete_project_happy_path(client: TestClient, record_property):
    """Test deleting an existing project successfully (Happy Path)."""
    record_property("method", "DELETE")
    record_property("url", "/DeleteProject/{project_id}")
    
    # Create a test project
    payload = {
        "ProjectName": "DeleteProjectSuccess",
        "VendorName": "VendorDelete",
        "ProjectCode": "DP-01",
        "Tool": "CVD"
    }
    create_response = client.post("/CreateProject", json=payload)
    assert create_response.status_code == 201
    project_id = create_response.json().get("ProjectID")
    
    # Delete the project
    response = client.delete(f"/DeleteProject/{project_id}")
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    data = response.json()
    assert data.get("ProjectID") == project_id
    assert data.get("Status") == "deleted"
    
    # Verify it can no longer be loaded
    load_response = client.get(f"/LoadProject/{project_id}")
    assert load_response.status_code == 404

def test_delete_project_not_found(client: TestClient, record_property):
    """Test deleting a project that does not exist (HTTP 404)."""
    record_property("method", "DELETE")
    record_property("url", "/DeleteProject/{project_id}")
    
    non_existent_id = 99999
    response = client.delete(f"/DeleteProject/{non_existent_id}")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_delete_project_invalid_id_type(client: TestClient, record_property):
    """Test validation failure when project_id is not an integer (HTTP 422)."""
    record_property("method", "DELETE")
    record_property("url", "/DeleteProject/{project_id}")
    
    response = client.delete("/DeleteProject/abc")
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422
