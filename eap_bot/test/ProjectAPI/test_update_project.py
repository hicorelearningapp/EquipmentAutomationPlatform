import pytest
from fastapi.testclient import TestClient

def test_update_project_happy_path_partial(client: TestClient, record_property):
    """Test updating only a subset of fields (Happy Path)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateProject/{project_id}")
    
    # Create a test project first
    payload = {
        "ProjectName": "UpdateProjectPartial",
        "VendorName": "VendorOriginal",
        "ProjectCode": "UP-ORIG",
        "Tool": "CVD"
    }
    create_response = client.post("/CreateProject", json=payload)
    assert create_response.status_code == 201
    project_id = create_response.json().get("ProjectID")
    
    try:
        # Partial update
        update_payload = {
            "ProjectDescription": "Newly added description",
            "ProjectCode": "UP-PARTIAL-UPDATED"
        }
        response = client.put(f"/UpdateProject/{project_id}", json=update_payload)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("ProjectDescription") == "Newly added description"
        assert data.get("ProjectCode") == "UP-PARTIAL-UPDATED"
        assert data.get("ProjectName") == "UpdateProjectPartial" # Unchanged
        assert data.get("VendorName") == "VendorOriginal" # Unchanged
    finally:
        client.delete(f"/DeleteProject/{project_id}")

def test_update_project_happy_path_full(client: TestClient, record_property):
    """Test updating all fields (Happy Path)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateProject/{project_id}")
    
    payload = {
        "ProjectName": "UpdateProjectFull",
        "VendorName": "VendorOriginal",
        "ProjectCode": "UP-ORIG",
        "Tool": "CVD"
    }
    create_response = client.post("/CreateProject", json=payload)
    assert create_response.status_code == 201
    project_id = create_response.json().get("ProjectID")
    
    try:
        # Full update
        update_payload = {
            "ProjectName": "UpdateProjectFullNewName",
            "VendorName": "VendorNew",
            "ProjectCode": "UP-NEW-CODE",
            "ProjectDescription": "New desc",
            "Tool": "ETCH",
            "ProjectVersion": "2.0"
        }
        response = client.put(f"/UpdateProject/{project_id}", json=update_payload)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("ProjectName") == "UpdateProjectFullNewName"
        assert data.get("VendorName") == "VendorNew"
        assert data.get("ProjectCode") == "UP-NEW-CODE"
        assert data.get("ProjectDescription") == "New desc"
        assert data.get("Tool") == "ETCH"
        assert data.get("ProjectVersion") == "2.0"
    finally:
        client.delete(f"/DeleteProject/{project_id}")

def test_update_project_duplicate_name_conflict(client: TestClient, record_property):
    """Test updating a project name to one that already exists in another project (HTTP 409)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateProject/{project_id}")
    
    # Create two test projects
    p1 = client.post("/CreateProject", json={"ProjectName": "UpProj1", "VendorName": "V", "ProjectCode": "C1"})
    p2 = client.post("/CreateProject", json={"ProjectName": "UpProj2", "VendorName": "V", "ProjectCode": "C2"})
    
    pid1 = p1.json().get("ProjectID")
    pid2 = p2.json().get("ProjectID")
    
    try:
        # Try to rename project 2 to project 1's name (case-insensitive)
        update_payload = {
            "ProjectName": "upproj1"
        }
        response = client.put(f"/UpdateProject/{pid2}", json=update_payload)
        record_property("expected", 409)
        record_property("got", response.status_code)
        assert response.status_code == 409
        assert "already exists" in response.json().get("detail", "").lower()
    finally:
        if pid1:
            client.delete(f"/DeleteProject/{pid1}")
        if pid2:
            client.delete(f"/DeleteProject/{pid2}")

def test_update_project_not_found(client: TestClient, record_property):
    """Test updating a project that does not exist (HTTP 404)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateProject/{project_id}")
    
    non_existent_id = 99999
    update_payload = {"ProjectName": "DoesNotMatter"}
    response = client.put(f"/UpdateProject/{non_existent_id}", json=update_payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_update_project_invalid_id_type(client: TestClient, record_property):
    """Test validation failure when project_id is not an integer (HTTP 422)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateProject/{project_id}")
    
    update_payload = {"ProjectName": "DoesNotMatter"}
    response = client.put("/UpdateProject/abc", json=update_payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422

def test_update_project_invalid_enum_tool(client: TestClient, record_property):
    """Test validation failure with an invalid Tool enum option (HTTP 422)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateProject/{project_id}")
    
    # Create a project
    p = client.post("/CreateProject", json={"ProjectName": "UpProjVal", "VendorName": "V", "ProjectCode": "C"})
    pid = p.json().get("ProjectID")
    
    try:
        update_payload = {
            "Tool": "INVALID_TOOL_OPTION"
        }
        response = client.put(f"/UpdateProject/{pid}", json=update_payload)
        record_property("expected", 422)
        record_property("got", response.status_code)
        assert response.status_code == 422
    finally:
        client.delete(f"/DeleteProject/{pid}")
