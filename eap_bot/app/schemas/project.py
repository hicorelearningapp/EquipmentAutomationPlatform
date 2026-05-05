from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str


class ProjectOut(BaseModel):
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True


class SpecSummary(BaseModel):
    id: int
    tool_id: str
    tool_type: str
    filename: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectDetail(ProjectOut):
    specs: list[SpecSummary] = []
