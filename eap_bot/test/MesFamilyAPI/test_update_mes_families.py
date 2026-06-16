import pytest
from fastapi.testclient import TestClient

def test_update_mes_families_happy_path(client: TestClient, record_property):
    """Test updating MES Families with valid list and restoring original state."""
    record_property("method", "POST")
    record_property("url", "/UpdateMesFamilies")
    
    # 1. Fetch current families to restore later
    get_res = client.get("/GetMesFamilies")
    assert get_res.status_code == 200
    original_families = get_res.json()
    
    try:
        # Create a new list with a temporary family
        test_payload = [
            {
                "FamilyID": 1,
                "Family": "FactoryWorks",
                "DefaultProtocol": "SECS-II",
                "RequiresAck": True,
                "Description": "Test desc"
            },
            {
                "Family": "TempTestFamily",
                "DefaultProtocol": "GEM",
                "RequiresAck": False,
                "Description": "Temporary test family"
            }
        ]
        
        response = client.post("/UpdateMesFamilies", json=test_payload)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("Status") == "success"
        families_list = data.get("Families", [])
        families_names = [f["Family"] for f in families_list]
        assert "TempTestFamily" in families_names
        
    finally:
        # Restore original state
        client.post("/UpdateMesFamilies", json=original_families)

def test_update_mes_families_duplicate_family_name(client: TestClient, record_property):
    """Test validation fails when duplicate family names are passed (HTTP 400)."""
    record_property("method", "POST")
    record_property("url", "/UpdateMesFamilies")
    
    payload = [
        {"Family": "DuplicateName", "DefaultProtocol": "SECS"},
        {"Family": "duplicatename", "DefaultProtocol": "GEM"} # Test case insensitivity
    ]
    response = client.post("/UpdateMesFamilies", json=payload)
    record_property("expected", 400)
    record_property("got", response.status_code)
    assert response.status_code == 400
    assert "duplicate family name" in response.json().get("detail", "").lower()
