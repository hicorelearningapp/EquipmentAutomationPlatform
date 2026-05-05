import json
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import ProjectRepository, SpecRepository
from app.db import get_db
from app.managers.service_container import container
from app.schemas.secsgem import EquipmentSpec, ValidationReport

router = APIRouter(prefix="/equipment", tags=["equipment"])


def get_spec_repo(db: Session = Depends(get_db)) -> SpecRepository:
    return SpecRepository(db)


def get_project_repo(db: Session = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(db)


class AskRequest(BaseModel):
    query: str


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    project_id: Optional[int] = Form(None),
    repo: SpecRepository = Depends(get_spec_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf files are accepted")

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(400, "File exceeds MAX_UPLOAD_SIZE")

    # 1. Validate project_id if provided
    project_row = None
    if project_id is not None:
        project_row = project_repo.get(project_id)
        if not project_row:
            raise HTTPException(404, f"Project with id={project_id} not found")

    # 2. Parse from in-memory bytes
    text = container.parser.extract_text(BytesIO(contents))
    if not text.strip():
        raise HTTPException(400, "Could not extract any text from the PDF")

    spec = container.extractor.extract(text)
    report = container.validator.validate(spec)

    row = repo.save(
        filename=file.filename,
        raw_text=text,
        spec=spec,
        report=report,
        project_id=project_id,
    )

    # 5. Determine target folder
    projects_dir = Path(settings.PROJECTS_DIR)
    safe_tool_id = "".join(c for c in spec.tool_id if c.isalnum() or c in (" ", "_", "-")).strip()
    folder_name = f"{row.id}_{safe_tool_id}".replace(" ", "_")

    if project_row:
        safe_project = "".join(c for c in project_row.name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        spec_folder = projects_dir / safe_project / folder_name
    else:
        spec_folder = projects_dir / "_unassigned" / folder_name

    spec_folder.mkdir(parents=True, exist_ok=True)

    # 6. Save only the JSON assets into the folder (no PDF, no raw text)
    (spec_folder / "spec.json").write_text(spec.model_dump_json(indent=4), encoding="utf-8")
    (spec_folder / "report.json").write_text(report.model_dump_json(indent=4), encoding="utf-8")

    # 7. Add to common vector store with project metadata
    container.vector_store.add_document(
        text,
        metadata={
            "tool_id": spec.tool_id,
            "spec_id": row.id,
            "project_id": project_id or 0,
        },
    )

    return {
        "id": row.id,
        "project_id": project_id,
        "folder": str(spec_folder),
        "spec": spec.model_dump(),
        "report": report.model_dump(),
    }


@router.get("")
def list_all(repo: SpecRepository = Depends(get_spec_repo)):
    return [
        {
            "id": r.id,
            "tool_id": r.tool_id,
            "tool_type": r.tool_type,
            "filename": r.filename,
            "created_at": r.created_at.isoformat(),
        }
        for r in repo.list_all()
    ]


@router.get("/{spec_id}")
def get_one(spec_id: int, repo: SpecRepository = Depends(get_spec_repo)):
    row = repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Spec not found")
    return {
        "id": row.id,
        "spec": EquipmentSpec.model_validate_json(row.spec_json).model_dump(),
        "report": ValidationReport.model_validate_json(row.validation_json).model_dump(),
    }


@router.get("/{spec_id}/json")
def download_json(spec_id: int, repo: SpecRepository = Depends(get_spec_repo)):
    row = repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Spec not found")
    headers = {
        "Content-Disposition": f'attachment; filename="{row.tool_id}_spec.json"'
    }
    return Response(content=row.spec_json, media_type="application/json", headers=headers)


@router.post("/{spec_id}/ask")
def ask(spec_id: int, body: AskRequest, repo: SpecRepository = Depends(get_spec_repo)):
    row = repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Spec not found")
    spec = EquipmentSpec.model_validate_json(row.spec_json)
    answer_text, source = container.qa_service.answer(body.query, spec)
    return {"answer": answer_text, "source": source}
