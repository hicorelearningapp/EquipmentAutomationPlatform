from fastapi import APIRouter, Depends, HTTPException

from app.schemas.project import ProjectCreate, ProjectDetail, ProjectOut
from app.services.storage_service import (
    InvalidSlugError,
    ProjectExistsError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)

router = APIRouter(prefix="/projects", tags=["projects"])


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
