from pydantic import BaseModel, Field
from typing import List, Optional, Any

class MESTag(BaseModel):
    tag_id: str
    name: str
    description: str = ""
    expected_type: str = ""
    expected_unit: str = ""

class MappingEntry(BaseModel):
    EquipmentFieldName: str
    EquipmentID: str = ""
    EntityType: str # variable, event, or alarm
    MESField: str
    Confidence: float
    Reasoning: str = ""
    Method: str = "llm"

class UnmappedEntity(BaseModel):
    EquipmentFieldName: str
    EquipmentID: str = ""
    EntityType: str
    Name: str

class MappingSuggestionResponse(BaseModel):
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

class SaveMappingRequest(BaseModel):
    project_id: Optional[int] = None
    family: str
    template: str
    Mappings: List[MappingEntry] = Field(default_factory=list)


class MESMappingRequest(BaseModel):
    family: str
    template: str


from typing import Dict

from source.schemas.secsgem import EquipmentSpec



class AutoMapSectionRequest(BaseModel):
    Events: list[dict] = Field(default_factory=list)
    Variables: list[dict] = Field(default_factory=list)
    Alarms: list[dict] = Field(default_factory=list)

    model_config = {
        "extra": "allow" # allow extra keys to be passed through
    }
