import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.crud import MappingTemplateRepository, SpecRepository
from app.db import get_db
from app.managers.service_container import container
from app.schemas.mapping import (
    CompletenessReport,
    EquipmentMapping,
    MappingEntry,
    MappingSuggestionRequest,
    MappingSuggestionResponse,
    MappingTemplateCreate,
    MappingTemplateOut,
    UnmappedEntity,
)
from app.schemas.secsgem import EquipmentSpec

router = APIRouter(prefix="/mapping", tags=["mapping"])


def get_spec_repo(db: Session = Depends(get_db)) -> SpecRepository:
    return SpecRepository(db)


def get_template_repo(db: Session = Depends(get_db)) -> MappingTemplateRepository:
    return MappingTemplateRepository(db)


@router.post("/{spec_id}/suggest", response_model=MappingSuggestionResponse)
def suggest(
    spec_id: int,
    request: MappingSuggestionRequest,
    spec_repo: SpecRepository = Depends(get_spec_repo),
):
    row = spec_repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Equipment spec not found")

    spec = EquipmentSpec.model_validate_json(row.spec_json)
    return container.mapping_service.suggest_mappings(spec, request.target_tags)


@router.post("/{spec_id}/approve", response_model=EquipmentMapping)
def approve(
    spec_id: int,
    mapping_data: EquipmentMapping,
    spec_repo: SpecRepository = Depends(get_spec_repo),
):
    row = spec_repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Equipment spec not found")

    mapping_data.spec_id = spec_id
    mapping_data.is_approved = True
    mapping_data.approved_at = datetime.utcnow()

    updated_row = spec_repo.save_mapping(spec_id, mapping_data)
    if not updated_row:
        raise HTTPException(500, "Failed to save mapping")
        
    return EquipmentMapping.model_validate_json(updated_row.mapping_json)


@router.get("/{spec_id}", response_model=EquipmentMapping)
def get_current_mapping(
    spec_id: int, 
    spec_repo: SpecRepository = Depends(get_spec_repo)
):
    row = spec_repo.get(spec_id)
    if not row or not row.mapping_json:
        raise HTTPException(404, "No mapping found for this equipment")
    return EquipmentMapping.model_validate_json(row.mapping_json)


@router.get("/{spec_id}/export")
def export_mapping(
    spec_id: int,
    spec_repo: SpecRepository = Depends(get_spec_repo),
):
    row = spec_repo.get(spec_id)
    if not row or not row.mapping_json:
        raise HTTPException(404, "No approved mapping found for this equipment")
    if not row.mapping_is_approved:
        raise HTTPException(400, "Mapping has not been approved yet. Approve it before exporting.")

    mapping = EquipmentMapping.model_validate_json(row.mapping_json)
    spec = EquipmentSpec.model_validate_json(row.spec_json)

    export_payload = {
        "export_timestamp": datetime.utcnow().isoformat(),
        "equipment": {
            "spec_id": row.id,
            "tool_id": spec.tool_id,
            "tool_type": spec.tool_type,
            "filename": row.filename,
        },
        "approved_at": row.mapping_approved_at.isoformat() if row.mapping_approved_at else None,
        "mappings": [entry.model_dump() for entry in mapping.mappings],
    }

    filename = f"{spec.tool_id}_mapping_export.json".replace(" ", "_")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=json.dumps(export_payload, indent=4),
        media_type="application/json",
        headers=headers,
    )


@router.post("/{spec_id}/save-template", response_model=MappingTemplateOut)
def save_as_template(
    spec_id: int,
    body: MappingTemplateCreate,
    spec_repo: SpecRepository = Depends(get_spec_repo),
    template_repo: MappingTemplateRepository = Depends(get_template_repo),
):
    row = spec_repo.get(spec_id)
    if not row or not row.mapping_json:
        raise HTTPException(404, "No mapping found for this equipment")
    if not row.mapping_is_approved:
        raise HTTPException(400, "Only approved mappings can be saved as templates")

    mapping = EquipmentMapping.model_validate_json(row.mapping_json)
    template_row = template_repo.save(
        name=body.name,
        tool_type=body.tool_type,
        mappings=mapping.mappings,
        source_spec_id=spec_id,
    )
    return _to_template_out(template_row)


@router.get("/templates", response_model=list[MappingTemplateOut])
def list_templates(
    tool_type: Optional[str] = None,
    template_repo: MappingTemplateRepository = Depends(get_template_repo),
):
    if tool_type:
        rows = template_repo.list_by_tool_type(tool_type)
    else:
        rows = template_repo.list_all()
    return [_to_template_out(r) for r in rows]


@router.get("/templates/{template_id}", response_model=MappingTemplateOut)
def get_template(
    template_id: int,
    template_repo: MappingTemplateRepository = Depends(get_template_repo),
):
    row = template_repo.get(template_id)
    if not row:
        raise HTTPException(404, "Template not found")
    return _to_template_out(row)


@router.post("/{spec_id}/apply-template/{template_id}", response_model=EquipmentMapping)
def apply_template(
    spec_id: int,
    template_id: int,
    spec_repo: SpecRepository = Depends(get_spec_repo),
    template_repo: MappingTemplateRepository = Depends(get_template_repo),
):
    row = spec_repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Equipment spec not found")

    template_row = template_repo.get(template_id)
    if not template_row:
        raise HTTPException(404, "Template not found")

    entries = [MappingEntry(**e) for e in json.loads(template_row.template_json)]
    pre_mapping = EquipmentMapping(
        spec_id=spec_id,
        mappings=entries,
        is_approved=False,
    )
    updated = spec_repo.save_mapping(spec_id, pre_mapping)
    return EquipmentMapping.model_validate_json(updated.mapping_json)


@router.get("/{spec_id}/completeness", response_model=CompletenessReport)
def check_completeness(
    spec_id: int,
    spec_repo: SpecRepository = Depends(get_spec_repo),
):
    row = spec_repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Equipment spec not found")
    if not row.mapping_json:
        raise HTTPException(400, "No mapping exists for this spec yet. Run /suggest first.")

    spec = EquipmentSpec.model_validate_json(row.spec_json)
    mapping = EquipmentMapping.model_validate_json(row.mapping_json)
    mapped_entity_ids = {e.entity_id for e in mapping.mappings}

    unmapped = []
    for v in spec.variables:
        if v.vid not in mapped_entity_ids:
            unmapped.append(UnmappedEntity(
                entity_id=v.vid,
                entity_type="variable",
                name=v.name,
                reason="Variable has no approved mapping",
            ))

    total = len(spec.variables)
    mapped = total - len(unmapped)
    is_complete = len(unmapped) == 0 and row.mapping_is_approved

    return CompletenessReport(
        spec_id=spec_id,
        is_complete=is_complete,
        ready_for_codegen=is_complete,
        total_entities=total,
        mapped_count=mapped,
        unmapped_entities=unmapped,
    )


def _to_template_out(row) -> MappingTemplateOut:
    mappings = [MappingEntry(**e) for e in json.loads(row.template_json)]
    return MappingTemplateOut(
        id=row.id,
        name=row.name,
        tool_type=row.tool_type,
        source_spec_id=row.source_spec_id,
        created_at=row.created_at,
        mappings=mappings,
    )
