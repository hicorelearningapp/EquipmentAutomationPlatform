from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator

from app.schemas.report import ReportDefinition, EventReportLink


class StatusVariable(BaseModel):
    SVID: int
    Name: str
    Description: Optional[str] = None
    DataType: str
    AccessType: str
    Value: Optional[str] = None
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class DataVariable(BaseModel):
    DvID: int
    Name: str
    ValueType: str
    Unit: Optional[str] = None


class RCMDParameter(BaseModel):
    Name: str
    Type: str


class RemoteCommand(BaseModel):
    RCMD: str
    Description: Optional[str] = None
    Parameters: list[RCMDParameter] = Field(default_factory=list)
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Event(BaseModel):
    CEID: int
    Name: str
    Description: Optional[str] = None
    LinkedVIDs: list[int] = Field(default_factory=list)
    ReportID: Optional[str] = None
    Report: bool = True
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Alarm(BaseModel):
    AlarmID: int
    Name: str
    Severity: str
    LinkedVID: Optional[int] = None
    Description: Optional[str] = None
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class State(BaseModel):
    StateID: str
    Name: str
    Description: Optional[str] = None


class StateTransition(BaseModel):
    FromState: str
    ToState: str
    TriggerEvent: Optional[str] = None
    TriggerCommand: Optional[str] = None
    Manual: bool = False

    @model_validator(mode="after")
    def at_least_one_trigger(self) -> "StateTransition":
        if not (self.TriggerEvent or self.TriggerCommand or self.Manual):
            self.Manual = True
        return self


class EquipmentSpec(BaseModel):
    DocumentType: Optional[str] = None
    ToolID: str
    ToolType: str
    Model: Optional[str] = None
    Protocol: str = "SECS/GEM"
    StatusVariables: list[StatusVariable] = Field(default_factory=list)
    DataVariables: list[DataVariable] = Field(default_factory=list)
    Events: list[Event] = Field(default_factory=list)
    Alarms: list[Alarm] = Field(default_factory=list)
    RemoteCommands: list[RemoteCommand] = Field(default_factory=list)
    States: list[State] = Field(default_factory=list)
    StateTransitions: list[StateTransition] = Field(default_factory=list)
    Reports: list[ReportDefinition] = Field(default_factory=list)
    EventReportLinks: list[EventReportLink] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    Severity: str
    Code: str
    Message: str
    EntityID: Optional[str] = None


class ValidationReport(BaseModel):
    Issues: list[ValidationIssue] = Field(default_factory=list)

    def is_clean(self) -> bool:
        return not any(i.Severity == "error" for i in self.Issues)
