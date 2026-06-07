import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from source.schemas.secsgem import EquipmentSpec
from source.services.storage_service import StorageService

def test_reanalyze_project_endpoint(client: TestClient, record_property):
    # 1. Create a project
    record_property("method", "POST")
    record_property("url", "/CreateProject")
    
    project_payload = {
        "ProjectName": "TestReanalyzeProj",
        "VendorName": "TestVendor",
        "ProjectCode": "TestCode123",
        "Tool": "CVD"
    }
    response = client.post("/CreateProject", json=project_payload)
    assert response.status_code == 201
    project_data = response.json()
    project_id = project_data.get("ProjectID")
    
    storage = StorageService()
    
    try:
        # 2. Add a dummy document manually in metadata and mark it "completed"
        metadata = storage.get_project(project_id)
        
        from source.schemas.project import DocumentMetadata
        from datetime import datetime
        
        dummy_doc = DocumentMetadata(
            DocumentID="test_doc",
            DocumentType="GEM Manual",
            FileName="test_manual.pdf",
            FileSize=100.0,
            Pages=5,
            UploadDate=datetime.now(),
            UploadedBy="test",
            Status="completed"
        )
        metadata.Documents.append(dummy_doc)
        storage._write_metadata(metadata)
        
        # Create a dummy project_batch.json to simulate existing cache
        batch_path = storage.spec_json_path(project_id, "project_batch")
        dummy_spec = EquipmentSpec(ToolID="TestTool", ToolType="CVD")
        storage.save_spec_json(batch_path, dummy_spec)
        assert batch_path.exists()
        
        # 3. Mock aggregate_project_data to simulate processing
        # When called, it should simulate the analysis finishing by marking status back to completed
        def mock_aggregate(pid, auto_analyze=False):
            meta = storage.get_project(pid)
            for d in meta.Documents:
                if d.DocumentID == "test_doc":
                    d.Status = "completed"
            storage._write_metadata(meta)
            return meta, EquipmentSpec(ToolID="ReanalyzedTool", ToolType="CVD")
            
        with patch("source.managers.service_container.container.project_service.aggregate_project_data", side_effect=mock_aggregate):
            url_reanalyze = f"/ReAnalyzeProject/{project_id}"
            record_property("method", "POST")
            record_property("url", url_reanalyze)
            
            response_reanalyze = client.post(url_reanalyze)
            record_property("expected", 200)
            record_property("got", response_reanalyze.status_code)
            
            # Assertions
            assert response_reanalyze.status_code == 200
            data = response_reanalyze.json()
            
            # Verify the project_batch.json file was re-saved with new spec
            re_saved_spec = EquipmentSpec.model_validate_json(batch_path.read_text(encoding="utf-8"))
            assert re_saved_spec.ToolID == "ReanalyzedTool"
            
            # Verify the document status is still "completed" after re-analysis
            docs = data.get("Documents", [])
            assert len(docs) == 1
            assert docs[0].get("Status") == "completed"

    finally:
        # Cleanup project
        client.delete(f"/DeleteProject/{project_id}")

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))
