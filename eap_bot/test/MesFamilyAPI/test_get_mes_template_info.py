import pytest
from fastapi.testclient import TestClient

def test_get_mes_template_info_happy_path(client: TestClient, record_property):
    """Test retrieving template info for an existing family and template (Happy Path)."""
    record_property("method", "GET")
    record_property("url", "/GetMesTemplateInfo/{mes_family}/{template}")
    
    # "FactoryWorks" / "STANDARD_EVENT_MODEL.json" should exist
    response = client.get("/GetMesTemplateInfo/FactoryWorks/STANDARD_EVENT_MODEL.json")
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    assert isinstance(response.json(), dict)

def test_get_mes_template_info_family_not_found(client: TestClient, record_property):
    """Test retrieving info for non-existent family (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetMesTemplateInfo/{mes_family}/{template}")
    
    response = client.get("/GetMesTemplateInfo/NonExistentFamilyXYZ/STANDARD_EVENT_MODEL.json")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_get_mes_template_info_template_not_found(client: TestClient, record_property):
    """Test retrieving info for non-existent template (HTTP 404)."""
    record_property("method", "GET")
    record_property("url", "/GetMesTemplateInfo/{mes_family}/{template}")
    
    response = client.get("/GetMesTemplateInfo/FactoryWorks/non_existent_template.json")
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
