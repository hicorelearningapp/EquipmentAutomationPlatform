import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Body
from fastapi.responses import Response

from source.managers.service_container import container
from source.schemas.project import DocumentCategory
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
        self.router.get("/Analyze/{project_id}/{document_id}/report", tags=["documents"])(self.download_report)
        self.router.get("/GetVariable/{project_id}/{document_id}", tags=["documents"])(self.get_variable)
        self.router.delete("/DeleteDocument/{project_id}/{document_id}", tags=["documents"])(self.delete_document)
        self.router.post("/UpdateExtraction/{project_id}", tags=["documents"])(self.update_extraction)

    async def upload_document(
        self,
        project_id: int,
        file: UploadFile = File(...),
        document_type: DocumentCategory = Form(...),
    ):
        if not file.filename:
            raise HTTPException(400, "No filename provided")
        contents = await file.read()
        try:
            return container.document_service.upload_document(
                project_id, file.filename, contents, document_type
            )
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

    def download_report(self, project_id: int, document_id: str):
        try:
            document = self.storage.get_document(project_id, document_id)
            content = self.storage.read_spec_json(project_id, document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        headers = {
            "Content-Disposition": f'attachment; filename="{document_id}_{document.ToolID}.json"'
        }
        return Response(content=content, media_type="application/json", headers=headers)

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

    def update_extraction(self, project_id: int, spec: dict = Body(...)):
        from source.schemas.secsgem import EquipmentSpec
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