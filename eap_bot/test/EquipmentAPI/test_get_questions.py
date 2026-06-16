import pytest
from fastapi.testclient import TestClient

def test_get_questions_happy_path(client: TestClient, record_property):
    """Test fetching questions for an existing project (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/GetQuestions/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "GetQuestionsProj", "VendorName": "V", "ProjectCode": "Q1"})
    pid = p.json().get("ProjectID")
    
    try:
        response = client.get(f"/GetQuestions/{pid}")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert "Questions" in data
        assert isinstance(data["Questions"], list)
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_get_questions_not_found(client: TestClient, record_property):
    """Test fetching questions for non-existent project (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetQuestions/{project_id}")
    
    response = client.get("/GetQuestions/99999")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
