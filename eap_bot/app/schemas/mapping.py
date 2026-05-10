from pydantic import BaseModel, Field

class VariableMapping(BaseModel):
    MESTag: str
    SVID: str = ""
    CEID: str = ""
    Description: str = ""

class ProjectMapping(BaseModel):
    ProjectID: int
    Mappings: list[VariableMapping] = Field(default_factory=list)

class MappingUpdateRequest(BaseModel):
    MESTags: list[str] = Field(default_factory=list)
    MESTagDocumentIDs: list[str] = Field(default_factory=list)
