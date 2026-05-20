from pydantic import BaseModel

class GenerateTestScriptsRequest(BaseModel):
    filename: str
