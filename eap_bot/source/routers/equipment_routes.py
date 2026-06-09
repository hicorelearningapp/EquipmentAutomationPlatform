import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from source.managers.service_container import container
from source.schemas.project import GenerateReportsRequest
from source.schemas.secsgem import EquipmentSpec
from source.services.storage_service import (
    DocumentExistsError,
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)

logger = logging.getLogger(__name__)


class EquipmentAPI:
    def __init__(self):
        self.router = APIRouter()
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/UploadDocument/{project_id}", tags=["documents"])(self.upload_document)
        self.router.get("/Analyze/{project_id}/{document_id}", response_model_by_alias=False, tags=["documents"])(self.analyze)
        self.router.get("/AnalyzeProject/{project_id}", response_model_by_alias=False, tags=["documents"])(self.analyze_project)
        self.router.get("/GetVariable/{project_id}/{document_id}", tags=["documents"])(self.get_variable)
        self.router.delete("/DeleteDocument/{project_id}/{document_id}", tags=["documents"])(self.delete_document)
        self.router.post("/UpdateExtraction/{project_id}", tags=["documents"])(self.update_extraction)
        self.router.post("/GenerateReports/{project_id}", tags=["documents"])(self.generate_reports)
        self.router.post("/AddReports/{project_id}", tags=["documents"])(self.add_reports)

    async def upload_document(self, project_id: int, file: UploadFile = File(...)):
        if not file.filename:
            raise HTTPException(400, "No filename provided")
        contents = await file.read()
        try:
            return container.document_service.upload_document(project_id, file.filename, contents)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except DocumentExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def analyze(self, project_id: int, document_id: str):
        try:
            return container.document_service.analyze_document(project_id, document_id)
        except (InvalidSlugError, ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def analyze_project(self, project_id: int):
        try:
            metadata, aggregated = container.project_service.aggregate_project_data(project_id)
            return container.document_service._build_extraction_response(
                project_id, "project_batch", aggregated
            )
        except (InvalidSlugError, ProjectNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def get_variable(self, project_id: int, document_id: str, categories: str = None):
        try:
            return container.document_service.get_variables(project_id, document_id, categories)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (InvalidSlugError, ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def delete_document(self, project_id: int, document_id: str):
        try:
            self.storage.delete_document(project_id, document_id)
            from source.utils.embedder import VectorStoreManager
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            vector_store.remove_document(document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {"Status": "success", "Message": f"Document {document_id} deleted"}

    def update_extraction(self, project_id: int, spec):
        try:
            self.storage.increment_project_version(project_id)
            json_path = self.storage.spec_json_path(project_id, "project_batch")
            self.storage.save_spec_json(json_path, spec)
            return {"Status": "success", "Message": "Extraction updated successfully"}
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def generate_reports(self, project_id: int, body: GenerateReportsRequest):
        """Suggest GEM reports for the selected CEIDs. Does NOT persist anything.
        If ceids is empty, generates suggestions for all events in each completed document.
        Returns suggested ReportDefinition objects per document.
        """
        try:
            metadata = self.storage.get_project(project_id)
            suggestions: dict[str, list[dict]] = {}

            for doc in metadata.Documents:
                if doc.Status != "completed":
                    continue
                spec_json = self.storage.read_spec_json(project_id, doc.DocumentID)
                spec = EquipmentSpec.model_validate_json(spec_json)

                # Filter events to only the requested CEIDs (or all if none specified)
                if body.ceids:
                    filtered_spec = spec.model_copy(
                        update={"Events": [e for e in spec.Events if e.CEID in body.ceids]}
                    )
                else:
                    filtered_spec = spec

                reports = container.report_service.generate_synthetic_reports(filtered_spec)
                suggestions[doc.DocumentID] = [r.model_dump() for r in reports]

            return {"Status": "success", "SuggestedReports": suggestions}
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def add_reports(self, project_id: int, body: GenerateReportsRequest):
        """Generate GEM reports for the selected CEIDs and persist them to project_batch.json.
        If ceids is empty, generates and persists for all events in each completed document.
        Skips documents that already have reports saved.
        Returns the list of persisted ReportDefinition objects per document.
        """
        try:
            metadata = self.storage.get_project(project_id)
            added: dict[str, list[dict]] = {}

            for doc in metadata.Documents:
                if doc.Status != "completed":
                    continue
                spec_json = self.storage.read_spec_json(project_id, doc.DocumentID)
                spec = EquipmentSpec.model_validate_json(spec_json)

                # Filter events to only the requested CEIDs (or all if none specified)
                if body.ceids:
                    filtered_spec = spec.model_copy(
                        update={"Events": [e for e in spec.Events if e.CEID in body.ceids]}
                    )
                else:
                    filtered_spec = spec

                reports = container.report_service.generate_synthetic_reports(filtered_spec)

                # Merge: keep existing reports, append new ones (avoid duplicates by RPTID)
                existing_ids = {r.RPTID for r in spec.Reports}
                new_reports = [r for r in reports if r.RPTID not in existing_ids]
                spec.Reports = spec.Reports + new_reports

                json_path = self.storage.spec_json_path(project_id, doc.DocumentID)
                self.storage.save_spec_json(json_path, spec)
                added[doc.DocumentID] = [r.model_dump() for r in new_reports]

            return {"Status": "success", "AddedReports": added}
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc