from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class Variable(BaseModel):
    vid: str
    name: str
    type: Literal["float", "integer", "string", "boolean"]
    unit: Optional[str] = None
    category: Literal["SV", "DV"]
    access: Literal["read", "write", "read/write"] = "read"
    description: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class RCMDParameter(BaseModel):
    name: str
    type: str


class RemoteCommand(BaseModel):
    rcmd: str
    description: Optional[str] = None
    parameters: list[RCMDParameter] = []
    confidence: float = Field(ge=0.0, le=1.0)


class Event(BaseModel):
    ceid: str
    name: str
    description: Optional[str] = None
    linked_vids: list[str] = []
    report: bool = True
    confidence: float = Field(ge=0.0, le=1.0)


class Alarm(BaseModel):
    alarm_id: str
    name: str
    severity: Literal["critical", "warning", "info"]
    linked_vid: Optional[str] = None
    description: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class State(BaseModel):
    state_id: str
    name: str
    description: Optional[str] = None


class StateTransition(BaseModel):
    from_state: str
    to_state: str
    trigger_event: Optional[str] = None
    trigger_command: Optional[str] = None
    manual: bool = False

    @model_validator(mode="after")
    def at_least_one_trigger(self) -> "StateTransition":
        if not (self.trigger_event or self.trigger_command or self.manual):
            self.manual = True
        return self


class Connection(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    mode: Optional[str] = None


class EquipmentSpec(BaseModel):
    tool_id: str
    tool_type: str
    model: Optional[str] = None
    protocol: str = "SECS/GEM"
    connection: Optional[Connection] = None
    variables: list[Variable] = []
    events: list[Event] = []
    alarms: list[Alarm] = []
    remote_commands: list[RemoteCommand] = []
    states: list[State] = []
    state_transitions: list[StateTransition] = []


class ValidationIssue(BaseModel):
    severity: Literal["error", "warning"]
    code: str
    message: str
    entity_id: Optional[str] = None


class ValidationReport(BaseModel):
    issues: list[ValidationIssue] = []

    def is_clean(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)
