from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ToolType(str, Enum):
    NONE = "None"
    MOCVD = "MOCVD"
    CVD = "CVD"
    LITHO = "LITHO"
    ETCH = "ETCH"


class ProjectCreate(BaseModel):
    ProjectName: str = Field(min_length=1)
    VendorName: str
    Tool: ToolType
    ProjectVersion: str = "1.0"


class DocumentMetadata(BaseModel):
    DocumentId: str
    FileName: str
    FileSize: float = 0.0
    Pages: int = 0
    UploadDate: datetime
    UploadedBy: str = ""
    Status: str = "completed"
    DocumentPath: str
    json_path: str
    tool_id: str
    tool_type: str
    vector_indexed: bool = False


class ProjectOut(BaseModel):
    ProjectID: str
    ProjectName: str
    VendorName: str
    Tool: ToolType
    ProjectVersion: str
    CreatedAt: datetime
    LastUpdatedOn: datetime
    Status: str


class ProjectMetadata(ProjectOut):
    document_count: int = 0
    documents: list[DocumentMetadata] = Field(default_factory=list)


class ProjectDetail(ProjectMetadata):
    pass
