"""
MES tag mapping service — receives its LLM strategy via constructor injection.
"""
import json
import logging
from typing import List

from source.schemas.mapping import (
    MESTag, 
    MappingEntry, 
    MappingSuggestionResponse, 
    UnmappedEntity
)
from source.schemas.secsgem import EquipmentSpec
from source.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)


class MappingService:

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)


    def suggest_mappings(
        self, spec: EquipmentSpec, target_tags: List[MESTag]
    ) -> MappingSuggestionResponse:
        prompt = self._build_prompt(spec, target_tags)
        try:
            raw = self._llm.invoke(prompt).content
            if isinstance(raw, list):
                raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Primary mapping failed (%s) — retrying.", e)
            raw = self._llm_retry.invoke(prompt).content
            if isinstance(raw, list):
                raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
            data = json.loads(raw)

        sanitized_data = self._sanitize(data, spec, target_tags)
        
        response = MappingSuggestionResponse.model_validate(sanitized_data)
        response.unmapped = self._find_unmapped(spec, response.suggestions)
        return response



    def _find_unmapped(
        self, spec: EquipmentSpec, suggestions: List[MappingEntry]
    ) -> List[UnmappedEntity]:
        mapped_entity_ids = {s.entity_id for s in suggestions}
        unmapped = []

        for v in spec.StatusVariables:
            vid_str = str(v.SVID)
            if vid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    entity_id=vid_str,
                    entity_type="variable",
                    name=v.Name,
                ))
        for v in spec.DataVariables:
            vid_str = str(v.DvID)
            if vid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    entity_id=vid_str,
                    entity_type="variable",
                    name=v.Name,
                ))
        for e in spec.Events:
            ceid_str = str(e.CEID)
            if ceid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    entity_id=ceid_str,
                    entity_type="event",
                    name=e.Name,
                ))
        for a in spec.Alarms:
            alarm_id_str = str(a.AlarmID)
            if alarm_id_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    entity_id=alarm_id_str,
                    entity_type="alarm",
                    name=a.Name,
                ))
        return unmapped


    def _sanitize(
        self, data: dict, spec: EquipmentSpec, target_tags: List[MESTag]
    ) -> dict:
        valid_entity_ids: set[str] = set()
        for v in spec.StatusVariables:
            valid_entity_ids.add(str(v.SVID))
        for v in spec.DataVariables:
            valid_entity_ids.add(str(v.DvID))
        for e in spec.Events:
            valid_entity_ids.add(str(e.CEID))
        for a in spec.Alarms:
            valid_entity_ids.add(str(a.AlarmID))

        valid_tag_ids = {t.tag_id for t in target_tags}

        valid_suggestions = [
            s
            for s in data.get("suggestions", [])
            if (
                str(s.get("entity_id")) in valid_entity_ids
                and s.get("tag_id") in valid_tag_ids
                and s.get("confidence", 0) >= 0.4
            )
        ]
        data["suggestions"] = valid_suggestions
        return data

    def _build_prompt(self, spec: EquipmentSpec, target_tags: List[MESTag]) -> str:
        equipment_entities = []
        for v in spec.StatusVariables:
            equipment_entities.append({
                "entity_id": str(v.SVID),
                "entity_type": "variable",
                "name": v.Name,
                "description": v.Description or "",
                "type": v.DataType,
                "unit": "",
            })
        for v in spec.DataVariables:
            equipment_entities.append({
                "entity_id": str(v.DvID),
                "entity_type": "variable",
                "name": v.Name,
                "description": "",
                "type": v.ValueType,
                "unit": v.Unit or "",
            })
        for e in spec.Events:
            equipment_entities.append({
                "entity_id": str(e.CEID),
                "entity_type": "event",
                "name": e.Name,
                "description": e.Description or "",
            })
        for a in spec.Alarms:
            equipment_entities.append({
                "entity_id": str(a.AlarmID),
                "entity_type": "alarm",
                "name": a.Name,
                "description": a.Description or "",
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
