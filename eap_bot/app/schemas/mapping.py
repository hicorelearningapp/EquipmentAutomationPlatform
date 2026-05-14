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
