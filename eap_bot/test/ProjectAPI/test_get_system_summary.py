import pytest
from fastapi.testclient import TestClient

def test_get_system_summary_happy_path(client: TestClient, record_property):
    """Test retrieving system-wide summary statistics (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/GetSystemSummary")
    
    response = client.get("/GetSystemSummary")
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    data = response.json()
    assert "TotalProjects" in data
    assert "TotalSmlScripts" in data
    assert "TotalConnectedTools" in data
