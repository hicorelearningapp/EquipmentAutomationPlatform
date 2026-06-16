import io
import pytest
from fastapi.testclient import TestClient

def test_upload_document_happy_path(client: TestClient, record_property):
    """Test uploading a document to an existing project successfully."""
    record_property("method", "POST")
    record_property("url", "/UploadDocument/{project_id}")
    
    # Create project first
    p = client.post("/CreateProject", json={"ProjectName": "UploadDocProj", "VendorName": "V", "ProjectCode": "U1"})
    pid = p.json().get("ProjectID")
    
    try:
        file_content = b"This is some mock SECS/GEM manual text."
        file = {"file": ("manual.txt", io.BytesIO(file_content), "text/plain")}
        data = {"document_type": "User Manuals"}
        
        response = client.post(f"/UploadDocument/{pid}", files=file, data=data)
        record_property("expected", 200)
        record_property("got", response.status_code)
        assert response.status_code == 200
        
        res_json = response.json()
        assert "document_id" in res_json
        assert res_json.get("status") == "uploaded"
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_upload_document_invalid_category(client: TestClient, record_property):
    """Test uploading a document with an invalid document type category (HTTP 422)."""
    record_property("method", "POST")
    record_property("url", "/UploadDocument/{project_id}")
    
    p = client.post("/CreateProject", json={"ProjectName": "UploadDocProjFail", "VendorName": "V", "ProjectCode": "U2"})
    pid = p.json().get("ProjectID")
    
    try:
        file_content = b"Mock text."
        file = {"file": ("manual.txt", io.BytesIO(file_content), "text/plain")}
        data = {"document_type": "INVALID_CATEGORY_NAME"}
        
        response = client.post(f"/UploadDocument/{pid}", files=file, data=data)
        record_property("expected", 422)
        record_property("got", response.status_code)
        assert response.status_code == 422
    finally:
        client.delete(f"/DeleteProject/{pid}")

def test_upload_document_project_not_found(client: TestClient, record_property):
    """Test uploading a document to a non-existent project (HTTP 404)."""
    record_property("method", "POST")
    record_property("url", "/UploadDocument/{project_id}")
    
    file_content = b"Mock text."
    file = {"file": ("manual.txt", io.BytesIO(file_content), "text/plain")}
    data = {"document_type": "User Manuals"}
    
    response = client.post("/UploadDocument/99999", files=file, data=data)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
