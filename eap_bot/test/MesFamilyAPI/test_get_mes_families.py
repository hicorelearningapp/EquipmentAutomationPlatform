import pytest
from fastapi.testclient import TestClient

def test_get_mes_families_happy_path(client: TestClient, record_property):
    """Test retrieving list of MES Families (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/GetMesFamilies")
    
    response = client.get("/GetMesFamilies")
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
