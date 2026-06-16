import pytest
from fastapi.testclient import TestClient

def test_delete_document_not_found(client: TestClient, record_property):
    """Test deleting non-existent document or project (HTTP 404)."""
    record_property("method", "DELETE")
    record_property("url", "/DeleteDocument/{project_id}/{document_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "DelDocFailProj", "VendorName": "V", "ProjectCode": "D1"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.delete(f"/DeleteDocument/{pid}/non_existent_doc")
        record_property("expected", 404)
        record_property("got", response.status_code)
        assert response.status_code == 404
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_delete_document_project_not_found(client: TestClient, record_property):
    """Test deleting document on a non-existent project (HTTP 404)."""
    record_property("method", "DELETE")
    record_property("url", "/DeleteDocument/{project_id}/{document_id}")
    
    response = client.delete("/DeleteDocument/99999/some_doc")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
