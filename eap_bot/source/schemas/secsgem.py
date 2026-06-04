from typing import Literal, Optional, Any
from pydantic import BaseModel, Field, model_validator, field_validator

from source.schemas.report import ReportDefinition


class StatusVariable(BaseModel):
    SVID: int
    Name: str
    Description: Optional[str] = None
    DataType: str = "-"
    AccessType: str = "-"
    Value: Optional[str] = "-"
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @field_validator('Description', 'DataType', 'AccessType', 'Value', mode='before')
    @classmethod
    def replace_empty(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and str(v).strip().lower() in ("", "unknown", "n/a", "none")):
            return "-"
        return v


class DataVariable(BaseModel):
    DvID: int
    Name: str
    ValueType: str = "-"
    Unit: Optional[str] = "-"

    @field_validator('ValueType', 'Unit', mode='before')
    @classmethod
    def replace_empty(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and str(v).strip().lower() in ("", "unknown", "n/a", "none")):
            return "-"
        return v


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
    EventName: str = Field(alias="Name")
    Description: Optional[str] = None
    LinkedVIDs: list[int] = Field(default_factory=list)
    ReportID: Optional[str] = "-"
    Report: bool = True
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    
    @field_validator('Description', 'ReportID', mode='before')
    @classmethod
    def replace_empty(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and str(v).strip().lower() in ("", "unknown", "n/a", "none")):
            return "-"
        return v
    
    model_config = {
        "populate_by_name": True
    }


class Alarm(BaseModel):
    AlarmID: int
    AlarmName: str = Field(alias="Name")
    Severity: str = "-"
    LinkedVID: Optional[int] = None
    Description: Optional[str] = "-"
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    
    @field_validator('Severity', 'Description', mode='before')
    @classmethod
    def replace_empty(cls, v: Any) -> Any:
        if v is None or (isinstance(v, str) and str(v).strip().lower() in ("", "unknown", "n/a", "none")):
            return "-"
        return v
    
    model_config = {
        "populate_by_name": True
    }


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
    ToolID: Optional[str] = None
    ToolType: Optional[str] = None
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


class ValidationIssue(BaseModel):
    Severity: str
    Code: str
    Message: str
    EntityID: Optional[str] = None


class ValidationReport(BaseModel):
    Issues: list[ValidationIssue] = Field(default_factory=list)

    def is_clean(self) -> bool:
        return not any(i.Severity == "error" for i in self.Issues)
