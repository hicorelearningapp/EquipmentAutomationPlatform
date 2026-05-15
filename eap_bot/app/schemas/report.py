from pydantic import BaseModel, Field
from typing import Optional

class ReportDefinition(BaseModel):
    RPTID: str = Field(alias="rptid")
    Name: str = Field(alias="name")
    LinkedVIDs: list[int] = Field(default_factory=list, alias="linked_vids")
    Confidence: float = Field(default=0.7, ge=0.0, le=1.0, alias="confidence")
    Reasoning: Optional[str] = Field(default=None, alias="reasoning")

    model_config = {"populate_by_name": True}


class EventReportLink(BaseModel):
    CEID: int = Field(alias="ceid")
    EventName: str = Field(alias="event_name")
    RPTIDs: list[str] = Field(default_factory=list, alias="rptids")

    model_config = {"populate_by_name": True}


class ReportSuggestionResponse(BaseModel):
    ProjectID: int
    DocumentID: str
    Reports: list[ReportDefinition] = Field(default_factory=list)
    EventReportLinks: list[EventReportLink] = Field(default_factory=list)
    Strategy: str = ""  # "event_centric" or "shared"
    OverallConfidence: float = 0.0