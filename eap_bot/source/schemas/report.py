from pydantic import BaseModel, Field
from typing import Optional

class ReportDefinition(BaseModel):
    RPTID: str
    Name: str
    Items: list[int] = Field(default_factory=list)
    LinkedEvents: list[int] = Field(default_factory=list)
    Confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    Reasoning: Optional[str] = None


class ReportSuggestionResponse(BaseModel):
    ProjectID: int
    DocumentID: str
    Reports: list[ReportDefinition] = Field(default_factory=list)
    Strategy: str = ""  # "event_centric" or "shared"
    OverallConfidence: float = 0.0
