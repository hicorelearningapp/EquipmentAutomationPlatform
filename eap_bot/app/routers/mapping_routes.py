"""
Mapping routes — all service dependencies sourced from ServiceContainer.
No more `global _mapping_service` singleton hack.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.crud import MappingRepository, SpecRepository
from app.db import get_db
from app.managers.service_container import container
from app.schemas.mapping import (
    EquipmentMapping,
    MappingSuggestionRequest,
    MappingSuggestionResponse,
)
from app.schemas.secsgem import EquipmentSpec

router = APIRouter(prefix="/mapping", tags=["mapping"])


def get_spec_repo(db: Session = Depends(get_db)) -> SpecRepository:
    return SpecRepository(db)

def get_mapping_repo(db: Session = Depends(get_db)) -> MappingRepository:
    return MappingRepository(db)


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
    mapping_repo: MappingRepository = Depends(get_mapping_repo),
):
    row = spec_repo.get(spec_id)
    if not row:
        raise HTTPException(404, "Equipment spec not found")

    mapping_data.spec_id = spec_id
    mapping_data.is_approved = True
    mapping_data.approved_at = datetime.utcnow()

    db_row = mapping_repo.save(mapping_data)
    return EquipmentMapping.model_validate_json(db_row.mapping_json)


@router.get("/{spec_id}", response_model=EquipmentMapping)
def get_current_mapping(
    spec_id: int, 
    mapping_repo: MappingRepository = Depends(get_mapping_repo)
):
    db_row = mapping_repo.get_by_spec(spec_id)
    if not db_row:
        raise HTTPException(404, "No mapping found for this equipment")
    return EquipmentMapping.model_validate_json(db_row.mapping_json)
