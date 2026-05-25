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
    SML_SCRIPTS = "SML Scripts"


class VariableCategory(str, Enum):
    """Selectable variable categories for the GetVariable endpoint (renders as dropdown in Swagger)."""
    STATUS_VARIABLE = "StatusVariable"
    DATA_VARIABLE = "DataVariable"
    EVENT = "Event"
    ALARM = "Alarm"
    REMOTE_COMMAND = "RemoteCommand"
    STATE = "State"


class ProjectCreate(BaseModel):
    ProjectName: str = Field(min_length=1)
    VendorName: str = Field(min_length=1)
    ProjectCode: str = Field(min_length=1)
    ProjectDescription: Optional[str] = None
    Tool: ToolType = ToolType.NONE


class DocumentMetadata(BaseModel):
    DocumentID: str = Field(alias="document_id")
    DocumentType: DocumentCategory = Field(alias="document_type")
    FileName: str = Field(alias="filename")
    FileSize: float = Field(default=0.0, alias="file_size")
    Pages: int = Field(default=0, alias="pages")
    UploadDate: datetime = Field(alias="upload_date")
    UploadedBy: str = Field(default="", alias="uploaded_by")
    ProjectCode: str = Field(default="", alias="project_code")
    ProjectDescription: str = Field(default="", alias="project_description")
    Status: str = Field(default="completed", alias="status")

    model_config = {
        "populate_by_name": True
    }


class ProjectOut(BaseModel):
    ProjectID: int = Field(alias="project_id")
    ProjectName: str = Field(alias="project_name")
    VendorName: str = Field(default="", alias="vendor_name")
    ProjectCode: str = Field(default="", alias="project_code")
    ProjectDescription: Optional[str] = Field(default=None, alias="project_description")
    Tool: ToolType = Field(alias="tool")
    CreatedAt: datetime = Field(alias="created_at")
    LastUpdatedOn: datetime = Field(alias="last_updated_on")
    Status: str = Field(alias="status")
    ProjectVersion: str = Field(default="1.0", alias="project_version")

    model_config = {
        "populate_by_name": True
    }


class ProjectMetadata(ProjectOut):
    Documents: list[DocumentMetadata] = Field(default_factory=list, alias="documents")

    model_config = {
        "populate_by_name": True
    }


class AggregatedSpec(BaseModel):
    StatusVariables: list[Any] = Field(default_factory=list)
    DataVariables: list[Any] = Field(default_factory=list)
    Events: list[Any] = Field(default_factory=list)
    Alarms: list[Any] = Field(default_factory=list)
    RemoteCommands: list[Any] = Field(default_factory=list)
    States: list[Any] = Field(default_factory=list)
    StateTransitions: list[Any] = Field(default_factory=list)
    Reports: list[Any] = Field(default_factory=list)
    EventReportLinks: list[Any] = Field(default_factory=list)

class ProjectDetail(ProjectMetadata):
    Extractions: AggregatedSpec = Field(default_factory=AggregatedSpec)
    Mappings: list[Any] = Field(default_factory=list)
    SmlTemplate: Any = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    ProjectName: Optional[str] = None
    ProjectDescription: Optional[str] = None
    VendorName: Optional[str] = None
    ProjectCode: Optional[str] = None
    Tool: Optional[ToolType] = None
    ProjectVersion: Optional[str] = None


class AskRequest(BaseModel):
    Category: str
    Question: str


class ProjectDetailsResponse(BaseModel):
    Id: int
    ProjectName: str
    ProjectCode: str
    ProjectDescription: Optional[str] = None
    VendorName: Optional[str] = None
    Tool: Optional[str] = None
    CreatedAt: datetime
    NumberOfDocuments: int
    NumberOfSVs: int
    NumberOfDVs: int
    NumberOfRemoteCommands: int
    NumberOfXMLFiles: int
    NumberOfReports: int
    NumberOfAlarms: int
    NumberOfEvents: int
