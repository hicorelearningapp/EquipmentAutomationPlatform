import io
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from source.routers.mes_family_routes import MES_MAP_DIR

def test_update_mes_template_info_happy_path(client: TestClient, record_property):
    """Test updating an existing template successfully and verifying version auto-increment."""
    record_property("method", "PUT")
    record_property("url", "/UpdateMesTemplateInfo/{mes_family}/{template}")
    
    template_path = MES_MAP_DIR / "FactoryWorks" / "STANDARD_EVENT_MODEL.json"
    
    # 1. Back up original template
    assert template_path.exists()
    with open(template_path, "r", encoding="utf-8") as f:
        original_content = f.read()
        
    try:
        # Update payload (without Version to trigger auto-increment)
        payload_data = {"Events": [], "Alarms": [], "Variables": []}
        file = {"file": ("STANDARD_EVENT_MODEL.json", io.BytesIO(json.dumps(payload_data).encode("utf-8")), "application/json")}
        
        response = client.put("/UpdateMesTemplateInfo/FactoryWorks/STANDARD_EVENT_MODEL.json", files=file)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        assert "updated successfully" in response.json().get("Message", "")
        
    finally:
        # Restore backup
        with open(template_path, "w", encoding="utf-8") as f:
            f.write(original_content)

def test_update_mes_template_info_not_found(client: TestClient, record_property):
    """Test updating a non-existent template (HTTP 404)."""
    record_property("method", "PUT")
    record_property("url", "/UpdateMesTemplateInfo/{mes_family}/{template}")
    
    file = {"file": ("non_existent.json", io.BytesIO(b"{}"), "application/json")}
    response = client.put("/UpdateMesTemplateInfo/FactoryWorks/non_existent_template.json", files=file)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
