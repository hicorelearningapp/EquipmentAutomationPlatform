from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class StatusVariable(BaseModel):
    SVID: int = Field(alias="svid")
    Name: str = Field(alias="name")
    Description: Optional[str] = Field(default=None, alias="description")
    DataType: str = Field(alias="data_type")
    AccessType: str = Field(alias="access_type")
    Value: Optional[str] = Field(default=None, alias="value")
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0, alias="confidence")

    model_config = {
        "populate_by_name": True
    }


class DataVariable(BaseModel):
    DvID: int = Field(alias="dvid")
    Name: str = Field(alias="name")
    ValueType: str = Field(alias="value_type")
    Unit: Optional[str] = Field(default=None, alias="unit")

    model_config = {
        "populate_by_name": True
    }


class RCMDParameter(BaseModel):
    Name: str = Field(alias="name")
    Type: str = Field(alias="type")

    model_config = {
        "populate_by_name": True
    }


class RemoteCommand(BaseModel):
    RCMD: str = Field(alias="rcmd")
    Description: Optional[str] = Field(default=None, alias="description")
    Parameters: list[RCMDParameter] = Field(default_factory=list, alias="parameters")
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0, alias="confidence")

    model_config = {
        "populate_by_name": True
    }


class Event(BaseModel):
    CEID: int = Field(alias="ceid")
    Name: str = Field(alias="name")
    Description: Optional[str] = Field(default=None, alias="description")
    LinkedVIDs: list[int] = Field(default_factory=list, alias="linked_vids")
    Report: bool = Field(default=True, alias="report")
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0, alias="confidence")

    model_config = {
        "populate_by_name": True
    }


class Alarm(BaseModel):
    AlarmID: int = Field(alias="alarm_id")
    Name: str = Field(alias="name")
    Severity: str = Field(alias="severity")
    LinkedVID: Optional[int] = Field(default=None, alias="linked_vid")
    Description: Optional[str] = Field(default=None, alias="description")
    Confidence: float = Field(default=1.0, ge=0.0, le=1.0, alias="confidence")

    model_config = {
        "populate_by_name": True
    }


class State(BaseModel):
    StateID: str = Field(alias="state_id")
    Name: str = Field(alias="name")
    Description: Optional[str] = Field(default=None, alias="description")

    model_config = {
        "populate_by_name": True
    }


class StateTransition(BaseModel):
    FromState: str = Field(alias="from_state")
    ToState: str = Field(alias="to_state")
    TriggerEvent: Optional[str] = Field(default=None, alias="trigger_event")
    TriggerCommand: Optional[str] = Field(default=None, alias="trigger_command")
    Manual: bool = Field(default=False, alias="manual")

    model_config = {
        "populate_by_name": True
    }

    @model_validator(mode="after")
    def at_least_one_trigger(self) -> "StateTransition":
        if not (self.TriggerEvent or self.TriggerCommand or self.Manual):
            self.Manual = True
        return self


class ConnectionInfo(BaseModel):
    Host: Optional[str] = Field(default=None, alias="host")
    Port: Optional[int] = Field(default=None, alias="port")
    Mode: Optional[str] = Field(default=None, alias="mode")

    model_config = {
        "populate_by_name": True
    }


class EquipmentSpec(BaseModel):
    ToolID: str = Field(alias="tool_id")
    ToolType: str = Field(alias="tool_type")
    Model: Optional[str] = Field(default=None, alias="model")
    Protocol: str = Field(default="SECS/GEM", alias="protocol")
    Connection: Optional[ConnectionInfo] = Field(default=None, alias="connection")
    StatusVariables: list[StatusVariable] = Field(default_factory=list, alias="StatusVariable")
    DataVariables: list[DataVariable] = Field(default_factory=list, alias="DataVariable")
    Events: list[Event] = Field(default_factory=list, alias="events")
    Alarms: list[Alarm] = Field(default_factory=list, alias="alarms")
    RemoteCommands: list[RemoteCommand] = Field(default_factory=list, alias="remote_commands")
    States: list[State] = Field(default_factory=list, alias="states")
    StateTransitions: list[StateTransition] = Field(default_factory=list, alias="state_transitions")

    model_config = {
        "populate_by_name": True
    }


class ValidationIssue(BaseModel):
    Severity: str = Field(alias="severity")
    Code: str = Field(alias="code")
    Message: str = Field(alias="message")
    EntityID: Optional[str] = Field(default=None, alias="entity_id")

    model_config = {
        "populate_by_name": True
    }


class ValidationReport(BaseModel):
    Issues: list[ValidationIssue] = Field(default_factory=list, alias="issues")

    model_config = {
        "populate_by_name": True
    }

    def is_clean(self) -> bool:
        return not any(i.Severity == "error" for i in self.Issues)
