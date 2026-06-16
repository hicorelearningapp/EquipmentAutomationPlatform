import io
import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from source.routers.mes_family_routes import MES_MAP_DIR

def test_add_mes_template_info_happy_path(client: TestClient, record_property):
    """Test adding a new template JSON file successfully to a family."""
    record_property("method", "POST")
    record_property("url", "/AddMesTemplateInfo/{mes_family}")
    
    # We use "FactoryWorks" family
    file_name = "test_temp_added_model.json"
    file_content = b'{"Events": [], "Alarms": [], "Variables": []}'
    file = {"file": (file_name, io.BytesIO(file_content), "application/json")}
    
    try:
        response = client.post("/AddMesTemplateInfo/FactoryWorks", files=file)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        assert "added successfully" in response.json().get("Message", "")
        
    finally:
        # Cleanup file if created
        target_path = MES_MAP_DIR / "FactoryWorks" / file_name
        if target_path.exists():
            os.remove(target_path)

def test_add_mes_template_info_invalid_extension(client: TestClient, record_property):
    """Test validation failure when file does not have .json extension (HTTP 400)."""
    record_property("method", "POST")
    record_property("url", "/AddMesTemplateInfo/{mes_family}")
    
    file = {"file": ("model.txt", io.BytesIO(b"{}"), "text/plain")}
    response = client.post("/AddMesTemplateInfo/FactoryWorks", files=file)
    record_property("expected", 400)
    record_property("got", response.status_code)
    assert response.status_code == 400
    assert "only .json files" in response.json().get("detail", "").lower()

def test_add_mes_template_info_family_not_found(client: TestClient, record_property):
    """Test adding a template to a non-existent family (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/AddMesTemplateInfo/{mes_family}")
    
    file = {"file": ("model.json", io.BytesIO(b"{}"), "application/json")}
    response = client.post("/AddMesTemplateInfo/NonExistentFamilyXYZ", files=file)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
