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
        from source.services.cosine_mapper import CosineSimilarityMapper
        
        # 1. Vector Pass (Fast Path)
        vector_mappings, unresolved_tags, unresolved_entities = CosineSimilarityMapper.map_tags(spec, target_tags)

        # 2. LLM Pass (Fallback)
        llm_data = {"Suggestions": []}
        if unresolved_tags:
            prompt = self._build_prompt(unresolved_entities, unresolved_tags, spec)
            try:
                raw = self._llm.invoke(prompt).content
                if isinstance(raw, list):
                    raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
                llm_data = json.loads(raw)
            except Exception as e:
                logger.warning("Primary mapping failed (%s) — retrying.", e)
                raw = self._llm_retry.invoke(prompt).content
                if isinstance(raw, list):
                    raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
                llm_data = json.loads(raw)

            llm_data = self._sanitize(llm_data, spec, unresolved_tags)

        # 3. Combine results
        combined_suggestions = []
        # Convert vector mappings to dicts so they match LLM output format before pydantic validation
        for vm in vector_mappings:
            combined_suggestions.append(vm.model_dump())
        
        for ls in llm_data.get("Suggestions", []):
            ls["Method"] = "llm"
            combined_suggestions.append(ls)

        final_data = {
            "EquipmentID": spec.ToolID,
            "Suggestions": combined_suggestions
        }
        
        response = MappingSuggestionResponse.model_validate(final_data)
        response.Unmapped = self._find_unmapped(spec, response.Suggestions)
        return response



    def _find_unmapped(
        self, spec: EquipmentSpec, suggestions: List[MappingEntry]
    ) -> List[UnmappedEntity]:
        mapped_entity_ids = {s.EntityID for s in suggestions}
        unmapped = []

        for v in spec.StatusVariables:
            vid_str = str(v.SVID)
            if vid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EntityID=vid_str,
                    EquipmentID=spec.ToolID,
                    EntityType="variable",
                    Name=v.Name,
                ))
        for v in spec.DataVariables:
            vid_str = str(v.DvID)
            if vid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EntityID=vid_str,
                    EquipmentID=spec.ToolID,
                    EntityType="variable",
                    Name=v.Name,
                ))
        for e in spec.Events:
            ceid_str = str(e.CEID)
            if ceid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EntityID=ceid_str,
                    EquipmentID=spec.ToolID,
                    EntityType="event",
                    Name=e.Name,
                ))
        for a in spec.Alarms:
            alarm_id_str = str(a.AlarmID)
            if alarm_id_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EntityID=alarm_id_str,
                    EquipmentID=spec.ToolID,
                    EntityType="alarm",
                    Name=a.Name,
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

        # Build a lookup for transaction
        tag_transactions = {t.tag_id: t.transaction for t in target_tags}

        valid_suggestions = []
        for s in data.get("Suggestions", []):
            if (
                str(s.get("EntityID")) in valid_entity_ids
                and s.get("TagID") in valid_tag_ids
                and s.get("Confidence", 0) >= 0.4
            ):
                tag_id = s.get("TagID")
                # Inject transaction and equipment ID from target tags / spec
                if tag_transactions.get(tag_id):
                    s["Transaction"] = tag_transactions[tag_id]
                s["EquipmentID"] = spec.ToolID
                valid_suggestions.append(s)

        data["Suggestions"] = valid_suggestions
        data["EquipmentID"] = spec.ToolID
        return data

    def _build_prompt(self, unresolved_entities: List[dict], target_tags: List[MESTag], spec: EquipmentSpec) -> str:
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
{json.dumps(unresolved_entities, indent=2)}

TARGET MES TAGS:
{json.dumps(mes_tags, indent=2)}

OUTPUT REQUIREMENT:
Provide a list of suggested mappings in JSON format.
Each mapping should include the `EntityID`, the `EntityType` (variable, event, or alarm), the `TagID`, a `Confidence` score (0.0 to 1.0), and a brief `Reasoning`.

HARD RULES:
1. Do not map entities if confidence is below 0.4.
2. Ensure data types match (e.g., do not map a float variable to a string MES tag unless explicitly required).
3. Do not invent or hallucinate IDs. Only use exact IDs provided in the lists above.

JSON SCHEMA:
{schema}

TOOL ID: {spec.ToolID}

Only output the JSON object. No prose.
"""
