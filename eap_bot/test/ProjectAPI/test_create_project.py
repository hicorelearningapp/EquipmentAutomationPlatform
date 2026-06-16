import pytest
from fastapi.testclient import TestClient
from source.schemas.project import ToolType

def test_create_project_happy_path(client: TestClient, record_property):
    """Test creating a project with valid inputs (Happy Path)."""
    record_property("method", "POST")
    record_property("url", "/CreateProject")
    
    payload = {
        "ProjectName": "UniqueHappyProject",
        "VendorName": "VendorHappy",
        "ProjectCode": "HP-01",
        "ProjectDescription": "Happy path testing description",
        "Tool": "MOCVD"
    }
    
    try:
        response = client.post("/CreateProject", json=payload)
        record_property("expected", 201)
        record_property("got", response.status_code)
        assert response.status_code == 201
        
        data = response.json()
        assert data.get("ProjectName") == "UniqueHappyProject"
        assert data.get("VendorName") == "VendorHappy"
        assert data.get("ProjectCode") == "HP-01"
        assert data.get("Tool") == "MOCVD"
        assert data.get("ProjectID") is not None
    finally:
        if "data" in locals() and data.get("ProjectID"):
            client.delete(f"/DeleteProject/{data['ProjectID']}")

def test_create_project_duplicate_name(client: TestClient, record_property):
    """Test creating a project with a name that already exists (HTTP 409)."""
    record_property("method", "POST")
    record_property("url", "/CreateProject")
    
    payload1 = {
        "ProjectName": "DuplicateProj",
        "VendorName": "Vendor1",
        "ProjectCode": "DUP-01",
        "Tool": "CVD"
    }
    payload2 = {
        "ProjectName": "duplicateproj",  # Test case-insensitivity
        "VendorName": "Vendor2",
        "ProjectCode": "DUP-02",
        "Tool": "ETCH"
    }
    
    response1 = client.post("/CreateProject", json=payload1)
    assert response1.status_code == 201
    pid = response1.json().get("ProjectID")
    
    try:
        response2 = client.post("/CreateProject", json=payload2)
        record_property("expected", 409)
        record_property("got", response2.status_code)
        assert response2.status_code == 409
        assert "already exists" in response2.json().get("detail", "")
    finally:
        if pid:
            client.delete(f"/DeleteProject/{pid}")

@pytest.mark.parametrize(
    "missing_field",
    ["ProjectName", "VendorName", "ProjectCode"]
)
def test_create_project_missing_required_fields(client: TestClient, missing_field, record_property):
    """Test validation failure when a required field is missing (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/CreateProject")
    
    payload = {
        "ProjectName": "MissingFieldProj",
        "VendorName": "VendorX",
        "ProjectCode": "MF-01",
        "Tool": "LITHO"
    }
    payload.pop(missing_field)
    
    response = client.post("/CreateProject", json=payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422

@pytest.mark.parametrize(
    "invalid_field,invalid_value",
    [
        ("ProjectName", ""),
        ("VendorName", ""),
        ("ProjectCode", ""),
        ("Tool", "INVALID_TOOL_TYPE"),
    ]
)
def test_create_project_invalid_field_values(client: TestClient, invalid_field, invalid_value, record_property):
    """Test validation failure with empty strings or invalid enum values (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/CreateProject")
    
    payload = {
        "ProjectName": "InvalidFieldProj",
        "VendorName": "VendorY",
        "ProjectCode": "IF-01",
        "Tool": "ETCH"
    }
    payload[invalid_field] = invalid_value
    
    response = client.post("/CreateProject", json=payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422

def test_create_project_invalid_types(client: TestClient, record_property):
    """Test validation failure when sending incorrect types like dictionaries for strings (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/CreateProject")
    
    payload_strict = {
        "ProjectName": {"name": "ComplexObject"},
        "VendorName": "VendorY",
        "ProjectCode": "IT-02"
    }
    response_strict = client.post("/CreateProject", json=payload_strict)
    record_property("expected", 422)
    record_property("got", response_strict.status_code)
    assert response_strict.status_code == 422
