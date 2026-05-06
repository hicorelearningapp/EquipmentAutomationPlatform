from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.managers.service_container import container
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectOut
from app.schemas.secsgem import EquipmentSpec
from app.services.storage_service import (
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectExistsError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)
from app.utils.embedder import VectorStoreManager

router = APIRouter(prefix="/projects", tags=["projects"])


class AskRequest(BaseModel):
    query: str = Field(min_length=1)


def get_storage() -> StorageService:
    try:
        return StorageService()
    except StorageError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("", response_model=ProjectDetail, status_code=201)
def create_project(
    body: ProjectCreate,
    storage: StorageService = Depends(get_storage),
):
    try:
        return storage.create_project(body.name)
    except InvalidSlugError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProjectExistsError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("", response_model=list[ProjectOut])
def list_projects(storage: StorageService = Depends(get_storage)):
    try:
        return storage.list_projects()
    except StorageError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.get("/{project_slug}", response_model=ProjectDetail)
def get_project(
    project_slug: str,
    storage: StorageService = Depends(get_storage),
):
    try:
        return storage.get_project(project_slug)
    except InvalidSlugError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ProjectNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.post("/{project_slug}/ask")
def ask(
    project_slug: str,
    body: AskRequest,
    storage: StorageService = Depends(get_storage),
):
    try:
        storage.get_project(project_slug)
        vector_store = VectorStoreManager(storage.vectorstore_path(project_slug))
        chunks = vector_store.search_with_filters(
            body.query, {"project_slug": project_slug}, k=1
        )
        if not chunks:
            raise HTTPException(404, "No indexed content in this project yet")

        document_id = chunks[0].metadata.get("document_id")
        if not document_id:
            raise HTTPException(500, "Indexed chunk is missing document_id metadata")

        spec_json = storage.read_spec_json(project_slug, document_id)
        spec = EquipmentSpec.model_validate_json(spec_json)
        qa_service = container.create_qa_service(
            vector_store,
            vector_filters={
                "project_slug": project_slug,
                "document_id": document_id,
            },
        )
        answer_text, source = qa_service.answer(body.query, spec)
    except InvalidSlugError as exc:
        raise HTTPException(400, str(exc)) from exc
    except (ProjectNotFoundError, DocumentNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from exc
    except StorageError as exc:
        raise HTTPException(500, str(exc)) from exc

    return {
        "project_slug": project_slug,
        "document_id": document_id,
        "answer": answer_text,
        "source": source,
    }
