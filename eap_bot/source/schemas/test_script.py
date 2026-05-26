from typing import Any
from pydantic import BaseModel

class GenerateTestScriptsRequest(BaseModel):
    filename: str

class GenerateTestSummaryRequest(BaseModel):
    tool_id: str
    ip_address: str
    secs_log: Any
    summary_json: Any
