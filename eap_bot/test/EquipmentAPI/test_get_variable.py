import pytest
from fastapi.testclient import TestClient

def test_get_variable_not_found(client: TestClient, record_property):
    """Test fetching variables for non-existent document or project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetVariable/{project_id}/{document_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "VarFailProj", "VendorName": "V", "ProjectCode": "V1"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.get(f"/GetVariable/{pid}/non_existent_doc")
        record_property("expected", 404)
        record_property("got", response.status_code)
        assert response.status_code == 404
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_get_variable_project_not_found(client: TestClient, record_property):
    """Test fetching variables on a non-existent project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetVariable/{project_id}/{document_id}")
    
    response = client.get("/GetVariable/99999/some_doc")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
