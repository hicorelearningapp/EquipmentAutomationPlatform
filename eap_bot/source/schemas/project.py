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
    ION_IMPLANTER = "ION_IMPLANTER"


class DocumentCategory(str, Enum):
    USER_MANUALS = "User Manuals"
    TROUBLESHOOTING_GUIDANCE = "Troubleshooting Guidance"
    GEM_MANUAL = "GEM Manual"
    VARIABLE_FILES = "Variable Files"
    LOG_FILES = "Log Files"
    ALARM_FILES = "Alarm Files"
    SML_SCRIPTS = "SML Scripts"
    MISCELLANEOUS = "Miscellaneous"


class TestResultFileType(str, Enum):
    test = "Test"
    secs_log = "SECSLog"


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
    ProjectDescription: Optional[str] = Field(default="")
    Tool: ToolType = ToolType.NONE


class DocumentMetadata(BaseModel):
    DocumentID: str = Field(alias="document_id")
    DocumentType: DocumentCategory = Field(alias="document_type")

    @field_validator("DocumentType", mode="before")
    def coerce_document_type(cls, v: Any) -> Any:
        if isinstance(v, str):
            mapping = {
                "user manual": DocumentCategory.USER_MANUALS,
                "variable file": DocumentCategory.VARIABLE_FILES,
                "log file": DocumentCategory.LOG_FILES,
                "log files": DocumentCategory.LOG_FILES,
                "alarm file": DocumentCategory.ALARM_FILES,
                "sml script": DocumentCategory.SML_SCRIPTS,
            }
            return mapping.get(v.strip().lower(), v)
        return v
    FileName: str = Field(alias="filename")
    FileSize: float = Field(default=0.0, alias="file_size")
    Pages: int = Field(default=0, alias="pages")
    UploadDate: datetime = Field(alias="upload_date")
    Status: str = Field(default="completed", alias="status")

    model_config = {
        "populate_by_name": True
    }


class ProjectOut(BaseModel):
    ProjectID: int = Field(alias="project_id")
    ProjectName: str = Field(alias="project_name")
    VendorName: str = Field(default="", alias="vendor_name")
    ProjectCode: str = Field(default="", alias="project_code")
    ProjectDescription: Optional[str] = Field(default="", alias="project_description")
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

class ProjectDetail(ProjectMetadata):
    Extractions: AggregatedSpec = Field(default_factory=AggregatedSpec)
    Mappings: dict[str, Any] = Field(default_factory=dict)
    SmlTemplate: Any = Field(default_factory=dict)
    Questions: list[dict[str, str]] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    ProjectName: Optional[str] = None
    ProjectDescription: Optional[str] = None
    VendorName: Optional[str] = None
    ProjectCode: Optional[str] = None
    Tool: Optional[ToolType] = None
    ProjectVersion: Optional[str] = None


class AskRequest(BaseModel):
    Question: str
    DocumentCategory: Optional[str] = None


class ProjectDetailsResponse(BaseModel):
    Id: int
    ProjectName: str
    ProjectCode: str
    ProjectDescription: Optional[str] = None
    VendorName: Optional[str] = None
    Tool: Optional[str] = None
    ProjectVersion: Optional[str] = None
    CreatedAt: datetime
    DocumentCount: int
    SVCount: int
    DVCount: int
    RCCount: int
    SmlScriptCount: int
    ReportCount: int
    AlarmCount: int
    EventCount: int

class SystemSummaryResponse(BaseModel):
    TotalProjects: int
    TotalSmlScripts: int
    TotalConnectedTools: int
    TotalScriptsTested: int = 0

class FrontendStatusVariable(BaseModel):
    SVID: int
    Name: str
    Description: Optional[str] = ""
    DataType: str
    AccessType: str
    Value: Optional[str] = ""
    Confidence: float = 0.0

class FrontendDataVariable(BaseModel):
    DvID: int
    Name: str
    Unit: Optional[str] = ""
    ValueType: str

class FrontendEvent(BaseModel):
    CEID: int
    EventName: str
    Description: Optional[str] = ""
    LinkedVIDs: list[int] = Field(default_factory=list)
    LinkedReports: list[str] = Field(default_factory=list)
    Confidence: float = 0.0

class FrontendAlarm(BaseModel):
    AlarmID: int
    AlarmName: str
    Severity: str
    LinkedVID: Optional[int] = None
    Description: Optional[str] = ""
    Confidence: float = 0.0

class FrontendRemoteCommand(BaseModel):
    RCMD: str
    Description: Optional[str] = ""
    Parameters: list[dict] = Field(default_factory=list)
    Confidence: float = 0.0

class UpdateExtractionRequest(BaseModel):
    ProjectID: int
    ExtractionID: str
    ConfidenceScore: float = 0.0
    ExtractionStatus: str = "completed"
    StatusVariables: list[FrontendStatusVariable] = Field(default_factory=list)
    DataVariables: list[FrontendDataVariable] = Field(default_factory=list)
    Events: list[FrontendEvent] = Field(default_factory=list)
    Alarms: list[FrontendAlarm] = Field(default_factory=list)
    RemoteCommands: list[FrontendRemoteCommand] = Field(default_factory=list)
    States: list[dict] = Field(default_factory=list)
    StateTransitions: list[dict] = Field(default_factory=list)
    Reports: list[dict] = Field(default_factory=list)

class GenerateReportsRequest(BaseModel):
    ceids: list[int] = Field(default_factory=list, description="List of CEIDs to generate reports for. If empty, generates for all events.")
