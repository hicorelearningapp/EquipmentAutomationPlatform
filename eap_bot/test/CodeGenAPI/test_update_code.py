import pytest
from fastapi.testclient import TestClient

def test_update_code_happy_path(client: TestClient, record_property):
    """Test updating project code on an existing project successfully."""
    record_property("method", "POST")
    record_property("url", "/UpdateCode/{project_id}")
    
    # Create project first
    p = client.post("/CreateProject", json={"ProjectName": "CodeGenProj", "VendorName": "V", "ProjectCode": "CG1"})
    pid = p.json().get("ProjectID")
    
    try:
        payload = {
            "Category": "sml",
            "SourceCode": "print('Hello SECS/GEM')"
        }
        response = client.post(f"/UpdateCode/{pid}", json=payload)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("ProjectID") == pid
        assert data.get("Category") == "sml"
        assert data.get("Status") == "success"
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_update_code_project_not_found(client: TestClient, record_property):
    """Test updating project code on a non-existent project (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/UpdateCode/{project_id}")
    
    payload = {
        "Category": "sml",
        "SourceCode": "print('Hello')"
    }
    response = client.post("/UpdateCode/99999", json=payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_update_code_validation_error(client: TestClient, record_property):
    """Test validation error with missing fields (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/UpdateCode/{project_id}")
    
    # Missing Category
    payload = {
        "SourceCode": "print('Hello')"
    }
    response = client.post("/UpdateCode/1", json=payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422
