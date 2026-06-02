from pydantic import BaseModel, Field
from typing import List, Optional, Any

class MESTag(BaseModel):
    tag_id: str
    name: str
    description: str = ""
    expected_type: str = ""
    expected_unit: str = ""
    transaction: Optional[str] = None

class MappingEntry(BaseModel):
    EntityID: str
    EquipmentID: str = ""
    EntityType: str # variable, event, or alarm
    TagID: str
    Transaction: Optional[str] = None
    Confidence: float
    Reasoning: str = ""
    Method: str = "llm"

class UnmappedEntity(BaseModel):
    EntityID: str
    EquipmentID: str = ""
    EntityType: str
    Name: str

class MappingSuggestionResponse(BaseModel):
    EquipmentID: str = ""
    Suggestions: List[MappingEntry] = Field(default_factory=list)
    Unmapped: List[UnmappedEntity] = Field(default_factory=list)

class VariableMapping(BaseModel):
    MESTag: str
    SVID: str = ""
    CEID: str = ""
    Description: str = ""

class ProjectMapping(BaseModel):
    ProjectID: int
    Mappings: List[VariableMapping] = Field(default_factory=list)

class MappingUpdateRequest(BaseModel):
    MESTags: List[str] = Field(default_factory=list)
    MESTagDocumentIDs: List[str] = Field(default_factory=list)


class MESMappingRequest(BaseModel):
    family: str
    template: str


from typing import Dict

from source.schemas.secsgem import EquipmentSpec

class AutoMapRequest(BaseModel):
    # ── Equipment side (provide ONE of these) ──────────────────────
    equipment_spec: Optional[EquipmentSpec] = None
    project_id: Optional[int] = None  # fallback: load from project batch spec

    # ── MES side (provide ONE of these) ────────────────────────────
    mes_template: Optional[Dict[str, Any]] = None
    family: Optional[str] = None      # fallback: load from template
    template: Optional[str] = None    # fallback: load from template

