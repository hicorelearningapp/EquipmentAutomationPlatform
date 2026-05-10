from pydantic import BaseModel
from typing import Any

class CodeUpdateRequest(BaseModel):
    Category: str
    SourceCode: str

class ResultUpdateRequest(BaseModel):
    Category: str
    Result: Any
