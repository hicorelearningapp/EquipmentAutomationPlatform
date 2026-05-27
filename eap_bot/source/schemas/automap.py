from typing import Optional
from pydantic import BaseModel, Field


class AutoMapRequest(BaseModel):
    project_id: int
    family: str
    template: str


class AutoMapAlternative(BaseModel):
    entity_id: str
    entity_type: str
    name: str
    confidence: float


class AutoMapSuggestion(BaseModel):
    tag_id: str
    tag_source: str             # "Variables" | "Events" | "Alarms" — where in the template the tag came from
    entity_id: str
    entity_type: str            # "variable" | "event" | "alarm"
    name: str                   # entity name, for UI convenience
    confidence: float
    method: str                 # "vector" | "llm_rerank"
    reasoning: Optional[str] = None
    alternatives: list[AutoMapAlternative] = Field(default_factory=list)


class NeedsReviewEntry(BaseModel):
    tag_id: str
    tag_source: str
    top_score: float
    reason: str                 # "low_confidence" | "no_compatible_candidates" | "no_entities_of_type"


class AutoMapStats(BaseModel):
    auto_accepted: int = 0
    llm_reranked: int = 0
    needs_review: int = 0
    total_tags: int = 0


class AutoMapBlock(BaseModel):
    """Goes into the template file's `AutoMapping` field. AutoMap owns it; overwrites freely."""
    generated_at: str
    project_id: int
    stats: AutoMapStats
    suggestions: list[AutoMapSuggestion] = Field(default_factory=list)
    needs_review: list[NeedsReviewEntry] = Field(default_factory=list)


class AutoMapResponse(BaseModel):
    auto_mapping: AutoMapBlock
    version: str                # template version after the write
    template_path: str
