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
    EquipmentField: str
    EquipmentID: str = ""
    EntityType: str # variable, event, or alarm
    MESField: str
    Transaction: Optional[str] = None
    Confidence: float
    Reasoning: str = ""
    Method: str = "llm"

class UnmappedEntity(BaseModel):
    EquipmentField: str
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

from enum import Enum

class AutoMapCategory(str, Enum):
    VARIABLES = "Variables"
    EVENTS = "Events"
    ALARMS = "Alarms"

class AutoMapRequest(BaseModel):
    project_id: int
    family: str
    template: str
    map_category: Optional[AutoMapCategory] = None

