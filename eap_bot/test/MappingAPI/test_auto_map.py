import pytest
from fastapi.testclient import TestClient

def test_auto_map_happy_path(client: TestClient, record_property):
    """Test AutoMap endpoint with query parameter project_id (Happy Path)."""
    record_property("method", "POST")
    record_property("url", "/AutoMap")
    
    # Create project first
    p = client.post("/CreateProject", json={"ProjectName": "AutoMapProj", "VendorName": "V", "ProjectCode": "AM1"})
    pid = p.json().get("ProjectID")
    
    try:
        payload = {
            "family": "FactoryWorks",
            "template": "STANDARD_EVENT_MODEL.json",
            "Events": [
                {
                    "MESEventName": "ChamberReady",
                    "EventName": ""
                }
            ],
            "Variables": [],
            "Alarms": []
        }
        
        # Call with query parameter project_id
        response = client.post(f"/AutoMap?project_id={pid}", json=payload)
        record_property("expected", 200)
        record_property("got", response.status_code)
        # It should return 200 and process the auto-map recommendations.
        assert response.status_code == 200
        assert "Events" in response.json()
        
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_auto_map_missing_project_id(client: TestClient, record_property):
    """Test AutoMap failure when project_id query parameter is missing (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/AutoMap")
    
    payload = {
        "family": "FactoryWorks",
        "template": "STANDARD_EVENT_MODEL.json"
    }
    response = client.post("/AutoMap", json=payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422

def test_auto_map_project_not_found(client: TestClient, record_property):
    """Test AutoMap for non-existent project (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/AutoMap")
    
    payload = {
        "family": "FactoryWorks",
        "template": "STANDARD_EVENT_MODEL.json"
    }
    response = client.post("/AutoMap?project_id=99999", json=payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_auto_map_filtered_response(client: TestClient):
    """Test AutoMap response contains only the items mentioned in the input body."""
    # Create project first
    p = client.post("/CreateProject", json={"ProjectName": "FilterTestProj", "VendorName": "V", "ProjectCode": "FT1"})
    pid = p.json().get("ProjectID")
    
    try:
        payload = {
            "family": "Camstar",
            "template": "STANDARD_EVENT_MODEL_NEW.json",
            "Events": [
                {
                    "MESEventName": "LotStart",
                    "EquipmentEventName": "",
                    "CEID": "",
                    "MESDescription": "Standard MES object for Lot Start",
                    "EquipmentDescription": "",
                    "Enabled": True,
                    "PayloadName": ""
                }
            ],
            "Variables": [],
            "Alarms": []
        }
        
        response = client.post(f"/AutoMap?project_id={pid}", json=payload)
        assert response.status_code == 200
        res_json = response.json()
        
        # Verify that only the single Event in the input is returned, and empty list for others
        assert len(res_json.get("Events", [])) == 1
        assert len(res_json.get("Variables", [])) == 0
        assert len(res_json.get("Alarms", [])) == 0
        assert res_json["Events"][0]["MESEventName"] == "LotStart"
        
    finally:
        client.delete(f"/DeleteProject/{pid}")

