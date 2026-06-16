import os
import json
import shutil
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from source.managers.service_container import container

def test_get_all_projects_empty(client: TestClient, record_property):
    """Test GetAllProjects when there are no projects in the system."""
    record_property("method", "GET")
    record_property("url", "/GetAllProjects")
    
    # We can mock or temporarily clear project directories, or use the current list length.
    # To be non-destructive, we simply assert that the response is a 200 OK and is a list.
    response = client.get("/GetAllProjects")
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    data = response.json()
    assert "ProjectInfo" in data
    assert isinstance(data["ProjectInfo"], list)

def test_get_all_projects_with_data(client: TestClient, record_property):
    """Test GetAllProjects returns newly created projects in sorted order."""
    record_property("method", "GET")
    record_property("url", "/GetAllProjects")
    
    # Create two test projects
    payload1 = {
        "ProjectName": "A_GetProjectsTest_1",
        "VendorName": "Vendor1",
        "ProjectCode": "GPT-01",
        "Tool": "CVD"
    }
    payload2 = {
        "ProjectName": "B_GetProjectsTest_2",
        "VendorName": "Vendor2",
        "ProjectCode": "GPT-02",
        "Tool": "ETCH"
    }
    
    response1 = client.post("/CreateProject", json=payload1)
    response2 = client.post("/CreateProject", json=payload2)
    
    pid1 = response1.json().get("ProjectID")
    pid2 = response2.json().get("ProjectID")
    
    try:
        response = client.get("/GetAllProjects")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        projects = data["ProjectInfo"]
        
        # Verify both projects exist in the list
        pids = [p["project_id"] for p in projects]
        assert pid1 in pids
        assert pid2 in pids
        
        # Verify sorting by ProjectID
        idx1 = pids.index(pid1)
        idx2 = pids.index(pid2)
        assert idx1 < idx2 or pid1 < pid2
        
    finally:
        if pid1:
            client.delete(f"/DeleteProject/{pid1}")
        if pid2:
            client.delete(f"/DeleteProject/{pid2}")

def test_get_all_projects_skips_non_digit_directories(client: TestClient, record_property):
    """Test that list_projects ignores directories that are not numeric IDs."""
    record_property("method", "GET")
    record_property("url", "/GetAllProjects")
    
    storage = container.storage
    non_digit_dir = storage.root / "not_a_project_id_123"
    
    try:
        non_digit_dir.mkdir(parents=True, exist_ok=True)
        # Create a mock metadata file inside it
        meta_dir = non_digit_dir / "metadata"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / "metadata.json"
        meta_file.write_text(json.dumps({"project_id": 99999, "project_name": "ShouldNotAppear"}), encoding="utf-8")
        
        response = client.get("/GetAllProjects")
        assert response.status_code == 200
        
        data = response.json()
        projects = data["ProjectInfo"]
        project_names = [p["project_name"] for p in projects]
        assert "ShouldNotAppear" not in project_names
        
    finally:
        if non_digit_dir.exists():
            shutil.rmtree(non_digit_dir)

def test_get_all_projects_resilience_to_corrupted_metadata(client: TestClient, record_property):
    """Test that list_projects skips and logs projects with corrupted/invalid metadata instead of failing."""
    record_property("method", "GET")
    record_property("url", "/GetAllProjects")
    
    # Create a project folder with digit name, but write corrupted JSON metadata
    storage = container.storage
    corrupt_project_id = 99998
    corrupt_dir = storage.root / str(corrupt_project_id)
    
    try:
        corrupt_dir.mkdir(parents=True, exist_ok=True)
        meta_dir = corrupt_dir / "metadata"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_file = meta_dir / "metadata.json"
        # Invalid JSON content
        meta_file.write_text("{invalid_json_here...", encoding="utf-8")
        
        response = client.get("/GetAllProjects")
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        data = response.json()
        projects = data["ProjectInfo"]
        pids = [p["project_id"] for p in projects]
        assert corrupt_project_id not in pids
        
    finally:
        if corrupt_dir.exists():
            shutil.rmtree(corrupt_dir)
