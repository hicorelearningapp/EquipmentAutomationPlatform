import pytest
from fastapi.testclient import TestClient

def test_ask_project_not_found(client: TestClient, record_property):
    """Test asking a question on a non-existent project (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/Ask/{project_id}")
    
    payload = {"Question": "What is the SVID for equipment status?"}
    response = client.post("/Ask/99999", json=payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_ask_project_empty_index(client: TestClient, record_property):
    """Test asking on a project that exists but has no documents/indexed content yet (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/Ask/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "AskEmptyProj", "VendorName": "V", "ProjectCode": "A1"})
    pid = p.json().get("ProjectID")
    
    try:
        payload = {"Question": "What is status?"}
        response = client.post(f"/Ask/{pid}", json=payload)
        record_property("expected", 404)
        record_property("got", response.status_code)
        assert response.status_code == 404
        assert "no indexed content" in response.json().get("detail", "").lower()
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_ask_project_invalid_id(client: TestClient, record_property):
    """Test parameter validation failure (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/Ask/{project_id}")
    
    payload = {"Question": "Hello?"}
    response = client.post("/Ask/abc", json=payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422

def test_ask_project_missing_payload(client: TestClient, record_property):
    """Test validation failure with missing required Question field (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/Ask/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "AskMissingPayload", "VendorName": "V", "ProjectCode": "A2"})
    pid = p.json().get("ProjectID")
    
    try:
        # Empty payload
        response = client.post(f"/Ask/{pid}", json={})
        record_property("expected", 422)
        record_property("got", response.status_code)
        assert response.status_code == 422
    finally:
        client.delete(f"/DeleteProject/{pid}")
