from pydantic import BaseModel

class SMLGenerationResponse(BaseModel):
    Status: str
    Message: str
    FileName: str
    DocumentID: str
    ScriptContent: str
