from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class MESTag(BaseModel):
    tag_id: str
    name: str
    description: Optional[str] = None
    expected_type: Optional[str] = None
    expected_unit: Optional[str] = None


class MappingEntry(BaseModel):
    entity_id: str = Field(..., description="The VID, CEID, or ALID from the equipment spec")
    entity_type: Literal["variable", "event", "alarm"] = Field(..., description="The type of equipment entity")
    tag_id: str = Field(..., description="The ID of the target MES tag")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: Optional[str] = Field(None, description="Explanation for the mapping suggestion")


class UnmappedEntity(BaseModel):
    entity_id: str
    entity_type: Literal["variable", "event", "alarm"]
    name: str
    reason: str = "No confident match found"


class EquipmentMapping(BaseModel):
    spec_id: int
    mappings: List[MappingEntry] = []
    is_approved: bool = False
    approved_at: Optional[datetime] = None


class MappingSuggestionRequest(BaseModel):
    target_tags: List[MESTag] = Field(..., description="List of MES tags to map against")


class MappingSuggestionResponse(BaseModel):
    suggestions: List[MappingEntry]
    unmapped: List[UnmappedEntity] = []


class MappingTemplateCreate(BaseModel):
    name: str
    tool_type: str


class MappingTemplateOut(BaseModel):
    id: int
    name: str
    tool_type: str
    source_spec_id: Optional[int]
    created_at: datetime
    mappings: List[MappingEntry] = []

    class Config:
        from_attributes = True


class CompletenessReport(BaseModel):
    spec_id: int
    is_complete: bool
    ready_for_codegen: bool
    total_entities: int
    mapped_count: int
    unmapped_entities: List[UnmappedEntity] = []
