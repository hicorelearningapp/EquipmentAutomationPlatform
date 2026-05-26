from typing import Any
from pydantic import BaseModel

class GenerateTestScriptsRequest(BaseModel):
    filename: str
