import pytest
from fastapi.testclient import TestClient

def test_get_knowledge_category_happy_path(client: TestClient, record_property):
    """Test retrieving knowledge categories for an existing project (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/GetKnowledgeCategory/{project_id}")
    
    # Create project
    p = client.post("/CreateProject", json={"ProjectName": "KnowledgeCatProj", "VendorName": "V", "ProjectCode": "K1"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.get(f"/GetKnowledgeCategory/{pid}")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_get_knowledge_category_not_found(client: TestClient, record_property):
    """Test retrieving categories for non-existent project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetKnowledgeCategory/{project_id}")
    
    response = client.get("/GetKnowledgeCategory/99999")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_get_knowledge_category_invalid_id(client: TestClient, record_property):
    """Test parameter validation failure (HTTP 422)."""
    record_property("method", "GET")
    record_property("url", "/GetKnowledgeCategory/{project_id}")
    
    response = client.get("/GetKnowledgeCategory/abc")
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422
