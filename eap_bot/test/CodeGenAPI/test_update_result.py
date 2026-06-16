import pytest
from fastapi.testclient import TestClient

def test_update_result_happy_path(client: TestClient, record_property):
    """Test updating results on a project successfully."""
    record_property("method", "POST")
    record_property("url", "/UpdateResult/{project_id}")
    
    payload = {
        "Category": "mapping",
        "Result": {"mapped_tags": 42}
    }
    response = client.post("/UpdateResult/1", json=payload)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    data = response.json()
    assert data.get("ProjectID") == 1
    assert data.get("Category") == "mapping"
    assert data.get("Status") == "success"
    assert data.get("Result") == {"mapped_tags": 42}

def test_update_result_validation_error(client: TestClient, record_property):
    """Test validation failure when category is missing from request body (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/UpdateResult/{project_id}")
    
    # Missing Category
    payload = {
        "Result": "some result"
    }
    response = client.post("/UpdateResult/1", json=payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422
