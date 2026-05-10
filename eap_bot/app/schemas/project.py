from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.secsgem import EquipmentSpec
from app.schemas.mapping import ProjectMapping


class ToolType(str, Enum):
    NONE = "None"
    MOCVD = "MOCVD"
    CVD = "CVD"
    LITHO = "LITHO"
    ETCH = "ETCH"


class DocumentType(str, Enum):
    USER_MANUALS = "User Manuals"
    TROUBLESHOOTING_GUIDANCE = "Troubleshooting Guidance"
    GEM_MANUAL = "GEM Manual"
    VARIABLE_FILES = "Variable Files"


class ProjectCreate(BaseModel):
    ProjectName: str = Field(min_length=1)
    VendorName: str
    Tool: ToolType


class DocumentMetadata(BaseModel):
    DocumentId: str
    DocumentType: DocumentType
    FileName: str
    FileSize: float = 0.0
    Pages: int = 0
    UploadDate: datetime
    UploadedBy: str = ""
    Status: str = "completed"
    DocumentPath: str
    JsonPath: str
    ToolId: str
    ToolType: str
    VectorIndexed: bool = False


class ProjectOut(BaseModel):
    ProjectID: str
    ProjectName: str
    VendorName: str
    Tool: ToolType
    CreatedAt: datetime
    LastUpdatedOn: datetime
    Status: str


class ProjectMetadata(ProjectOut):
    DocumentCount: int = 0
    Documents: list[DocumentMetadata] = Field(default_factory=list)


class ProjectDetail(ProjectMetadata):
    Extractions: list[EquipmentSpec] = Field(default_factory=list)
    Mappings: ProjectMapping = Field(default_factory=ProjectMapping)


class AskRequest(BaseModel):
    Category: str
    Question: str

