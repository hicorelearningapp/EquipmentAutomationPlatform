import pytest
from fastapi.testclient import TestClient

def test_analyze_document_not_found(client: TestClient, record_property):
    """Test analyzing a document that does not exist (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/Analyze/{project_id}/{document_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "AnalyzeFailProj", "VendorName": "V", "ProjectCode": "A1"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.get(f"/Analyze/{pid}/non_existent_doc")
        record_property("expected", 404)
        record_property("got", response.status_code)
        assert response.status_code == 404
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_analyze_document_invalid_project(client: TestClient, record_property):
    """Test analyzing a document on a non-existent project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/Analyze/{project_id}/{document_id}")
    
    response = client.get("/Analyze/99999/some_doc")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
