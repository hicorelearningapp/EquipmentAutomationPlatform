import pytest
from fastapi.testclient import TestClient

def test_project_details_flow(client: TestClient, record_property):
    # 1. Add Project with Code and Description
    record_property("method", "POST")
    record_property("url", "/AddProject")
    
    payload = {
        "ProjectName": "TestDetailsProj",
        "VendorName": "TestVendorName",
        "ProjectCode": "TD-PROJ-01",
        "ProjectDescription": "A test project for verification of project details",
        "Tool": "CVD"
    }
    
    response = client.post("/AddProject", json=payload)
    record_property("expected", 201)
    record_property("got", response.status_code)
    assert response.status_code == 201
    
    project_data = response.json()
    project_id = project_data.get("ProjectID")
    assert project_id is not None
    assert project_data.get("ProjectCode") == "TD-PROJ-01"
    assert project_data.get("ProjectDescription") == "A test project for verification of project details"

    try:
        # 2. Get Project Details
        url_details = f"/GetProjectDetails/{project_id}"
        record_property("method", "GET")
        record_property("url", url_details)
        
        response_details = client.get(url_details)
        record_property("expected", 200)
        record_property("got", response_details.status_code)
        assert response_details.status_code == 200
        
        details = response_details.json()
        assert details.get("Id") == project_id
        assert details.get("ProjectName") == "TestDetailsProj"
        assert details.get("ProjectCode") == "TD-PROJ-01"
        assert details.get("ProjectDescription") == "A test project for verification of project details"
        assert details.get("VendorName") == "TestVendorName"
        assert details.get("Tool") == "CVD"
        assert details.get("NumberOfDocuments") == 0
        assert details.get("NumberOfSVs") == 0
        
        # 3. Update Project
        url_update = f"/UpdateProject/{project_id}"
        record_property("method", "PUT")
        record_property("url", url_update)
        
        update_payload = {
            "ProjectCode": "TD-PROJ-UPDATED",
            "ProjectDescription": "Updated description"
        }
        response_update = client.put(url_update, json=update_payload)
        record_property("expected", 200)
        record_property("got", response_update.status_code)
        assert response_update.status_code == 200
        
        updated_data = response_update.json()
        assert updated_data.get("ProjectCode") == "TD-PROJ-UPDATED"
        assert updated_data.get("ProjectDescription") == "Updated description"
        
        # 4. Verify in Load Project
        url_load = f"/LoadProject/{project_id}"
        record_property("method", "GET")
        record_property("url", url_load)
        response_load = client.get(url_load)
        assert response_load.status_code == 200
        loaded_data = response_load.json()
        assert loaded_data.get("ProjectCode") == "TD-PROJ-UPDATED"
        assert loaded_data.get("ProjectDescription") == "Updated description"
        
    finally:
        # Cleanup
        client.delete(f"/DeleteProject/{project_id}")

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
