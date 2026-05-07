from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.config import settings
from app.managers.service_container import container
from app.services.storage_service import (
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)
from app.utils.embedder import VectorStoreManager


class EquipmentAPI:
    def __init__(self):
        self.router = APIRouter(
            prefix="/projects/{project_id}/equipment", tags=["equipment"]
        )
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/upload")(self.upload)
        self.router.get("/{document_id}/json")(self.download_json)
        self.router.delete("/{document_id}")(self.delete_document)

    async def upload(self, project_id: str, file: UploadFile = File(...)):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only .pdf files are accepted")

        contents = await file.read()
        if len(contents) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(400, "File exceeds MAX_UPLOAD_SIZE")

        try:
            document_id, pdf_path, json_path = self.storage.prepare_document_paths(
                project_id, file.filename
            )
            self.storage.save_pdf(pdf_path, contents)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        text = container.parser.extract_text(str(pdf_path))
        if not text.strip():
            raise HTTPException(400, "Could not extract any text from the PDF")

        spec = container.extractor.extract(text)
        report = container.validator.validate(spec)

        try:
            self.storage.save_spec_json(json_path, spec)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            vector_indexed = vector_store.add_document(
                text,
                metadata={
                    "project_id": project_id,
                    "document_id": document_id,
                    "tool_id": spec.tool_id,
                },
            )
            document = self.storage.add_document_metadata(
                project_id=project_id,
                document_id=document_id,
                original_filename=file.filename,
                spec=spec,
                vector_indexed=vector_indexed,
            )
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "project_id": project_id,
            "document_id": document_id,
            "pdf_path": document.pdf_path,
            "json_path": document.json_path,
            "vector_indexed": document.vector_indexed,
            "spec": spec.model_dump(),
            "validation": report.model_dump(),
        }

    def download_json(self, project_id: str, document_id: str):
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
            "Content-Disposition": f'attachment; filename="{document_id}_{document.tool_id}.json"'
        }
        return Response(content=content, media_type="application/json", headers=headers)

    def delete_document(self, project_id: str, document_id: str):
        try:
            self.storage.delete_document(project_id, document_id)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            removed = vector_store.remove_document(document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {
            "status": "success",
            "message": f"Document '{document_id}' deleted",
            "chunks_removed": removed,
        }
