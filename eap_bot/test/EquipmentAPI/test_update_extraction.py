import pytest
from fastapi.testclient import TestClient

def test_update_extraction_not_found(client: TestClient, record_property):
    """Test updating extraction for non-existent project (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/UpdateExtraction/{project_id}")
    
    payload = {
        "ProjectID": 99999,
        "ExtractionID": "project_batch",
        "ConfidenceScore": 0.95,
        "ExtractionStatus": "completed",
        "StatusVariables": [],
        "DataVariables": [],
        "Events": [],
        "Alarms": [],
        "RemoteCommands": [],
        "States": [],
        "StateTransitions": [],
        "Reports": []
    }
    response = client.post("/UpdateExtraction/99999", json=payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_update_extraction_invalid_payload(client: TestClient, record_property):
    """Test validation error when updating extraction with invalid schema fields (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/UpdateExtraction/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "UpExtractFail", "VendorName": "V", "ProjectCode": "UE1"})
    pid = p.json().get("ProjectID")
    
    try:
        # Invalid payload (missing required fields in StatusVariables)
        payload = {
            "ProjectID": pid,
            "ExtractionID": "project_batch",
            "StatusVariables": [{"SVID": "not_an_int"}] # should be integer SVID
        }
        response = client.post(f"/UpdateExtraction/{pid}", json=payload)
        record_property("expected", 422)
        record_property("got", response.status_code)
        assert response.status_code == 422
    finally:
        client.delete(f"/DeleteProject/{pid}")
