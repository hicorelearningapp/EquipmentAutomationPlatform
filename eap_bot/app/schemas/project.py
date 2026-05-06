from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1)


class DocumentMetadata(BaseModel):
    id: str
    original_filename: str
    pdf_path: str
    json_path: str
    tool_id: str
    tool_type: str
    uploaded_at: datetime
    extraction_status: str = "completed"
    vector_indexed: bool = False


class ProjectOut(BaseModel):
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
    document_count: int


class ProjectMetadata(ProjectOut):
    documents: list[DocumentMetadata] = Field(default_factory=list)


class ProjectDetail(ProjectMetadata):
    pass
