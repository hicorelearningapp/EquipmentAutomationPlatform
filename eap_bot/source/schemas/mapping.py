from pydantic import BaseModel, Field
from typing import List, Optional, Any

class MESTag(BaseModel):
    tag_id: str
    name: str
    description: str = ""
    expected_type: str = ""
    expected_unit: str = ""

class MappingEntry(BaseModel):
    entity_id: str
    entity_type: str # variable, event, or alarm
    tag_id: str
    confidence: float
    reasoning: str = ""

class UnmappedEntity(BaseModel):
    entity_id: str
    entity_type: str
    name: str

class MappingSuggestionResponse(BaseModel):
    suggestions: List[MappingEntry] = Field(default_factory=list)
    unmapped: List[UnmappedEntity] = Field(default_factory=list)

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


class TestEquipmentVariable(BaseModel):
    id: str                             # Entity identifier (SVID, DvID, CEID, AlarmID)
    name: str
    entity_type: str = "variable"       # "variable", "event", or "alarm"
    description: Optional[str] = None
    data_type: str = "String"


class TestMESVariable(BaseModel):
    tag_id: str                         # Unique ID (e.g. "EquipmentID", "LotStart")
    name: str                           # Display name
    entity_type: str = "variable"       # "variable", "event", or "alarm"
    description: str = ""
    expected_type: str = ""             # e.g. "String", "Integer"


class TestMappingRequest(BaseModel):
    # ── Equipment side (provide ONE of these) ──────────────────────
    equipment_variables: Optional[List[TestEquipmentVariable]] = None
    project_id: Optional[int] = None  # fallback: load from project batch spec

    # ── MES side (provide ONE of these) ────────────────────────────
    mes_variables: Optional[List[TestMESVariable]] = None
    family: Optional[str] = None      # fallback: load from template
    template: Optional[str] = None    # fallback: load from template

