from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class ToolType(str, Enum):
    NONE = "None"
    MOCVD = "MOCVD"
    CVD = "CVD"
    LITHO = "LITHO"
    ETCH = "ETCH"


class DocumentCategory(str, Enum):
    USER_MANUALS = "User Manuals"
    TROUBLESHOOTING_GUIDANCE = "Troubleshooting Guidance"
    GEM_MANUAL = "GEM Manual"
    VARIABLE_FILES = "Variable Files"


class ProjectCreate(BaseModel):
    ProjectName: str = Field(min_length=1)
    VendorName: str = Field(min_length=1)
    Tool: ToolType = ToolType.NONE
    ProjectVersion: str = "1.0"

    @field_validator("ProjectVersion", mode="before")
    def set_default_version(cls, v):
        if not v or str(v).strip() == "":
            return "1.0"
        return v


class DocumentMetadata(BaseModel):
    DocumentID: str = Field(alias="document_id")
    DocumentType: DocumentCategory = Field(alias="document_type")
    FileName: str = Field(alias="filename")
    FileSize: float = Field(default=0.0, alias="file_size")
    Pages: int = Field(default=0, alias="pages")
    UploadDate: datetime = Field(alias="upload_date")
    UploadedBy: str = Field(default="", alias="uploaded_by")
    Status: str = Field(default="completed", alias="status")
    DocumentPath: str = Field(alias="document_path")
    JsonPath: str = Field(alias="json_path")
    ToolID: str = Field(alias="tool_id")
    ToolType: str = Field(alias="tool_type")
    VectorIndexed: bool = Field(default=False, alias="vector_indexed")

    model_config = {
        "populate_by_name": True
    }


class ProjectOut(BaseModel):
    ProjectID: int = Field(alias="project_id")
    ProjectName: str = Field(alias="project_name")
    VendorName: str = Field(default="", alias="vendor_name")
    Tool: ToolType = Field(alias="tool")
    CreatedAt: datetime = Field(alias="created_at")
    LastUpdatedOn: datetime = Field(alias="last_updated_on")
    Status: str = Field(alias="status")
    ProjectVersion: str = Field(default="1.0", alias="project_version")

    model_config = {
        "populate_by_name": True
    }


class ProjectMetadata(ProjectOut):
    DocumentCount: int = Field(default=0, alias="document_count")
    Documents: list[DocumentMetadata] = Field(default_factory=list, alias="documents")

    model_config = {
        "populate_by_name": True
    }


class ProjectDetail(ProjectMetadata):
    Extractions: list[Any] = Field(default_factory=list)
    Mappings: list[Any] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    ProjectName: Optional[str] = None
    VendorName: Optional[str] = None
    Tool: Optional[ToolType] = None
    ProjectVersion: Optional[str] = None


class AskRequest(BaseModel):
    Category: str
    Question: str
