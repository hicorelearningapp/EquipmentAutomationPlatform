"""
MES tag mapping service — receives its LLM strategy via constructor injection.
"""
import json
import logging
from typing import List

from app.schemas.mapping import MESTag, MappingEntry, MappingSuggestionResponse
from app.schemas.secsgem import EquipmentSpec
from app.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)


class MappingService:
    """Suggests SECS/GEM-entity → MES-tag mappings using an LLM."""

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        # Dependencies injected — no hard-wired provider choice here.
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def suggest_mappings(
        self, spec: EquipmentSpec, target_tags: List[MESTag]
    ) -> MappingSuggestionResponse:
        prompt = self._build_prompt(spec, target_tags)
        try:
            raw = self._llm.invoke(prompt).content
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Primary mapping failed (%s) — retrying.", e)
            raw = self._llm_retry.invoke(prompt).content
            data = json.loads(raw)

        sanitized_data = self._sanitize(data, spec, target_tags)
        return MappingSuggestionResponse.model_validate(sanitized_data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _sanitize(
        self, data: dict, spec: EquipmentSpec, target_tags: List[MESTag]
    ) -> dict:
        """Remove hallucinated entity_ids / tag_ids and low-confidence entries."""
        valid_entity_ids: set[str] = set()
        for v in spec.variables:
            valid_entity_ids.add(v.vid)
        for e in spec.events:
            valid_entity_ids.add(e.ceid)
        for a in spec.alarms:
            valid_entity_ids.add(a.alarm_id)

        valid_tag_ids = {t.tag_id for t in target_tags}

        valid_suggestions = [
            s
            for s in data.get("suggestions", [])
            if (
                s.get("entity_id") in valid_entity_ids
                and s.get("tag_id") in valid_tag_ids
                and s.get("confidence", 0) >= 0.4
            )
        ]
        data["suggestions"] = valid_suggestions
        return data

    def _build_prompt(self, spec: EquipmentSpec, target_tags: List[MESTag]) -> str:
        equipment_entities = []
        for v in spec.variables:
            equipment_entities.append({
                "entity_id": v.vid,
                "entity_type": "variable",
                "name": v.name,
                "description": v.description,
                "type": v.type,
                "unit": v.unit,
            })
        for e in spec.events:
            equipment_entities.append({
                "entity_id": e.ceid,
                "entity_type": "event",
                "name": e.name,
                "description": e.description,
            })
        for a in spec.alarms:
            equipment_entities.append({
                "entity_id": a.alarm_id,
                "entity_type": "alarm",
                "name": a.name,
                "description": a.description,
            })

        mes_tags = [
            {
                "tag_id": t.tag_id,
                "name": t.name,
                "description": t.description,
                "expected_type": t.expected_type,
                "expected_unit": t.expected_unit,
            }
            for t in target_tags
        ]

        schema = json.dumps(MappingSuggestionResponse.model_json_schema(), indent=2)

        return f"""You are a semiconductor automation expert. Your task is to map Equipment Entities (Variables, Events, Alarms) to MES Tags.

EQUIPMENT ENTITIES:
{json.dumps(equipment_entities, indent=2)}

TARGET MES TAGS:
{json.dumps(mes_tags, indent=2)}

OUTPUT REQUIREMENT:
Provide a list of suggested mappings in JSON format.
Each mapping should include the `entity_id`, the `entity_type` (variable, event, or alarm), the `tag_id`, a `confidence` score (0.0 to 1.0), and a brief `reasoning`.

HARD RULES:
1. Do not map entities if confidence is below 0.4.
2. Ensure data types match (e.g., do not map a float variable to a string MES tag unless explicitly required).
3. Do not invent or hallucinate IDs. Only use exact IDs provided in the lists above.

JSON SCHEMA:
{schema}

Only output the JSON object. No prose.
"""
