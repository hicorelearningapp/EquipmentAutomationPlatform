from pydantic import BaseModel
from typing import Any, Optional

class CodeGenRequest(BaseModel):
    ProjectID: int
    FileName: str
    Language: str
    Instructions: Optional[str] = None

class CodeGenResponse(BaseModel):
    ProjectID: int
    Key: str # FileName
    Type: str # Language
    Code: str

class CodeUpdateRequest(BaseModel):
    Category: str
    SourceCode: str

class ResultUpdateRequest(BaseModel):
    Category: str
    Result: Any


class ScriptUpdateRequest(BaseModel):
    key: str
    script: str


class SmartCodeGenerateRequest(BaseModel):
    key: str
    instructions: Optional[str] = None


class SmartCodeUpdateRequest(BaseModel):
    key: str
    source_code: str
