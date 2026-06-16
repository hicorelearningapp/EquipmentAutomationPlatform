import pytest
from fastapi.testclient import TestClient

def test_get_mes_templates_happy_path(client: TestClient, record_property):
    """Test fetching templates for a valid MES family (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/GetMesTemplates/{mes_family}")
    
    # "FactoryWorks" is a default seeded family
    response = client.get("/GetMesTemplates/FactoryWorks")
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_get_mes_templates_family_not_found(client: TestClient, record_property):
    """Test fetching templates for non-existent family (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetMesTemplates/{mes_family}")
    
    response = client.get("/GetMesTemplates/NonExistentFamilyXYZ")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
