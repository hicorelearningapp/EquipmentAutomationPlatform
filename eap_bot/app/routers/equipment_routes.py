from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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

router = APIRouter(prefix="/projects/{project_slug}/equipment", tags=["equipment"])


def get_storage() -> StorageService:
    try:
        return StorageService()
    except StorageError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/upload")
async def upload(
    project_slug: str,
    file: UploadFile = File(...),
    storage: StorageService = Depends(get_storage),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf files are accepted")

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(400, "File exceeds MAX_UPLOAD_SIZE")

    try:
        document_id, pdf_path, json_path = storage.prepare_document_paths(
            project_slug, file.filename
        )
        storage.save_pdf(pdf_path, contents)
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
        storage.save_spec_json(json_path, spec)
        vector_store = VectorStoreManager(storage.vectorstore_path(project_slug))
        vector_indexed = vector_store.add_document(
            text,
            metadata={
                "project_slug": project_slug,
                "document_id": document_id,
                "tool_id": spec.tool_id,
            },
        )
        document = storage.add_document_metadata(
            project_slug=project_slug,
            document_id=document_id,
            original_filename=file.filename,
            spec=spec,
            vector_indexed=vector_indexed,
        )
    except StorageError as exc:
        raise HTTPException(500, str(exc)) from exc

    return {
        "project_slug": project_slug,
        "document_id": document_id,
        "pdf_path": document.pdf_path,
        "json_path": document.json_path,
        "vector_indexed": document.vector_indexed,
        "spec": spec.model_dump(),
        "validation": report.model_dump(),
    }


@router.get("/{document_id}/json")
def download_json(
    project_slug: str,
    document_id: str,
    storage: StorageService = Depends(get_storage),
):
    try:
        document = storage.get_document(project_slug, document_id)
        content = storage.read_spec_json(project_slug, document_id)
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
