"""
LLM rerank step for the ambiguous middle band of AutoMap.

Input: ONE MES tag + the top-K candidate entities the vector step already filtered.
Output: the chosen entity_id (must be from the candidate list) + confidence + reasoning,
        or `entity_id=None` if the LLM judges none of the candidates fit.

The prompt is deliberately small (~1 KB) — by the time we get here, hard-rule
filtering and top-K retrieval have already narrowed the search space. The LLM's
job is judgment, not search.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import List, Optional

from source.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)


@dataclass
class RerankCandidate:
    entity_id: str
    entity_type: str
    name: str
    description: str
    data_type: str
    unit: str
    cosine_score: float


@dataclass
class RerankResult:
    entity_id: Optional[str]    # None if LLM judged "none fit"
    confidence: float
    reasoning: str


_PROMPT = """You are mapping a single MES tag to the best matching equipment entity.

MES TAG:
{tag_block}

CANDIDATES (you MUST pick one of these by entity_id, or reply with entity_id="none" if all 5 are wrong):
{candidates_block}

Pick the candidate whose semantic meaning best matches the MES tag.
- A short name like "LotID" should match "CurrentLotId" (current lot identifier) even though the strings differ.
- Reject candidates that share keywords but mean a different thing (e.g. "RecipeName" vs "RecipeVersion" — those are NOT the same).
- If no candidate is a clear semantic match, return entity_id="none".

Output JSON (no prose):
{{
  "entity_id": "<id from the candidate list, or 'none'>",
  "confidence": <0.0 to 1.0>,
  "reasoning": "<one short sentence>"
}}
"""


def _format_tag(tag: dict) -> str:
    return (
        f"  tag_id:        {tag['tag_id']}\n"
        f"  section:       {tag.get('tag_source', '')}\n"
        f"  name:          {tag.get('name', '')}\n"
        f"  description:   {tag.get('description', '') or '(none)'}\n"
        f"  expected_type: {tag.get('expected_type', '') or '(none)'}\n"
        f"  expected_unit: {tag.get('expected_unit', '') or '(none)'}"
    )


def _format_candidates(cands: List[RerankCandidate]) -> str:
    lines = []
    for i, c in enumerate(cands, 1):
        lines.append(
            f"  [{i}] entity_id={c.entity_id}  type={c.entity_type}  "
            f"name={c.name!r}  data_type={c.data_type or '-'}  unit={c.unit or '-'}\n"
            f"      description: {c.description or '(none)'}\n"
            f"      cosine_score: {c.cosine_score:.3f}"
        )
    return "\n".join(lines)


class RerankService:

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)

    def rerank(self, tag: dict, candidates: List[RerankCandidate]) -> RerankResult:
        if not candidates:
            return RerankResult(entity_id=None, confidence=0.0, reasoning="no candidates")

        prompt = _PROMPT.format(
            tag_block=_format_tag(tag),
            candidates_block=_format_candidates(candidates),
        )
        try:
            raw = self._llm.invoke(prompt).content
            if isinstance(raw, list):
                raw = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in raw)
            data = json.loads(raw)
        except Exception as exc:
            logger.warning("Rerank LLM call failed for tag %s: %s", tag.get("tag_id"), exc)
            return RerankResult(entity_id=None, confidence=0.0, reasoning=f"rerank_error: {exc}")

        chosen = str(data.get("entity_id", "")).strip()
        confidence = float(data.get("confidence", 0.0) or 0.0)
        reasoning = str(data.get("reasoning", "")).strip()

        if chosen.lower() in ("none", "", "null"):
            return RerankResult(entity_id=None, confidence=confidence, reasoning=reasoning or "llm_rejected")

        # Enforce: the LLM may only pick from the candidate set
        valid_ids = {c.entity_id for c in candidates}
        if chosen not in valid_ids:
            logger.warning(
                "Rerank LLM returned out-of-set entity_id=%s for tag=%s; treating as rejection",
                chosen, tag.get("tag_id"),
            )
            return RerankResult(entity_id=None, confidence=0.0, reasoning="llm_returned_invalid_id")

        # Clamp confidence to [0, 1]
        confidence = max(0.0, min(1.0, confidence))
        return RerankResult(entity_id=chosen, confidence=confidence, reasoning=reasoning)
