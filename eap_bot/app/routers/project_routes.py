from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import ProjectRepository
from app.db import get_db
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectOut, SpecSummary

router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_repo(db: Session = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(db)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    repo: ProjectRepository = Depends(get_project_repo),
):
    existing = repo.get_by_name(body.name)
    if existing:
        raise HTTPException(409, f"A project named '{body.name}' already exists (id={existing.id})")
    return repo.create(body.name)


@router.get("", response_model=list[ProjectOut])
def list_projects(repo: ProjectRepository = Depends(get_project_repo)):
    return repo.list_all()


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: int,
    repo: ProjectRepository = Depends(get_project_repo),
):
    row = repo.get(project_id)
    if not row:
        raise HTTPException(404, "Project not found")

    specs = repo.list_specs(project_id)
    return ProjectDetail(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        specs=[
            SpecSummary(
                id=s.id,
                tool_id=s.tool_id,
                tool_type=s.tool_type,
                filename=s.filename,
                created_at=s.created_at,
            )
            for s in specs
        ],
    )
