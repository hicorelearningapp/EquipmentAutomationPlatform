import json
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.crud import SpecRepository
from app.db import get_db
from app.managers.service_container import container
from app.schemas.secsgem import EquipmentSpec, ValidationReport

router = APIRouter(prefix="/equipment", tags=["equipment"])


def get_spec_repo(db: Session = Depends(get_db)) -> SpecRepository:
    return SpecRepository(db)


class AskRequest(BaseModel):
    query: str


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    repo: SpecRepository = Depends(get_spec_repo)
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf files are accepted")

    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(400, "File exceeds MAX_UPLOAD_SIZE")

    # 1. Parse from in-memory bytes
    text = container.parser.extract_text(BytesIO(contents))
    if not text.strip():
        raise HTTPException(400, "Could not extract any text from the PDF")

    # 2. Extract spec and validate
    spec = container.extractor.extract(text)
    report = container.validator.validate(spec)

    # 3. Save to database to get the spec_id
    row = repo.save(filename=file.filename, raw_text=text, spec=spec, report=report)

    # 4. Create the final structured folder: specs_output/{spec_id}_{tool_id}/
    specs_dir = Path(settings.SPECS_OUTPUT_DIR)
    specs_dir.mkdir(parents=True, exist_ok=True)
    
    safe_tool_id = "".join(c for c in spec.tool_id if c.isalnum() or c in (" ", "_", "-")).strip()
    folder_name = f"{row.id}_{safe_tool_id}".replace(" ", "_")
    spec_folder = specs_dir / folder_name
    spec_folder.mkdir(parents=True, exist_ok=True)

    # 5. Save only the JSON assets into the folder (no PDF, no raw text)
    (spec_folder / "spec.json").write_text(spec.model_dump_json(indent=4), encoding="utf-8")
    (spec_folder / "report.json").write_text(report.model_dump_json(indent=4), encoding="utf-8")

    # 6. Add to common vector store
    container.vector_store.add_document(text, metadata={"tool_id": spec.tool_id, "spec_id": row.id})

    return {
        "id": row.id,
        "folder": folder_name,
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
