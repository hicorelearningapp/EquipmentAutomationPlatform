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
                print(f"DEBUG RAW PRIMARY LLM: {raw}")
                llm_data = json.loads(raw)
            except Exception as e:
                logger.warning("Primary mapping failed (%s) — retrying.", e)
                raw = self._llm_retry.invoke(prompt).content
                if isinstance(raw, list):
                    raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
                print(f"DEBUG RAW FALLBACK LLM: {raw}")
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
            "Suggestions": combined_suggestions
        }
        
        response = MappingSuggestionResponse.model_validate(final_data)
        response.Unmapped = self._find_unmapped(spec, response.Suggestions)
        return response



    def _find_unmapped(
        self, spec: EquipmentSpec, suggestions: List[MappingEntry]
    ) -> List[UnmappedEntity]:
        mapped_entity_ids = {s.EquipmentFieldName for s in suggestions}
        unmapped = []

        for v in spec.StatusVariables:
            vid_str = str(v.SVID)
            if vid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EquipmentFieldName=vid_str,
                    EntityType="variable",
                    Name=v.Name,
                ))
        for v in spec.DataVariables:
            vid_str = str(v.DvID)
            if vid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EquipmentFieldName=vid_str,
                    EntityType="variable",
                    Name=v.Name,
                ))
        for e in spec.Events:
            ceid_str = str(e.CEID)
            if ceid_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EquipmentFieldName=ceid_str,
                    EntityType="event",
                    Name=e.EventName,
                    
                ))
        for a in spec.Alarms:
            alarm_id_str = str(a.AlarmID)
            if alarm_id_str not in mapped_entity_ids:
                unmapped.append(UnmappedEntity(
                    EquipmentFieldName=alarm_id_str,
                    EntityType="alarm",
                    Name=a.AlarmName,
                ))
        return unmapped


    def _sanitize(
        self, data: dict, spec: EquipmentSpec, target_tags: List[MESTag]
    ) -> dict:
        entity_id_lookup = {}
        entity_name_lookup = {}
        
        for v in spec.StatusVariables:
            v_id = str(v.SVID)
            v_name = v.Name
            
            entity_id_lookup[v_id] = v_id
            if v_name: entity_id_lookup[v_name.lower()] = v_id
            
            entity_name_lookup[v_id] = v_name
            if v_name: entity_name_lookup[v_name.lower()] = v_name
            
        for v in spec.DataVariables:
            v_id = str(v.DvID)
            v_name = v.Name
            
            entity_id_lookup[v_id] = v_id
            if v_name: entity_id_lookup[v_name.lower()] = v_id
            
            entity_name_lookup[v_id] = v_name
            if v_name: entity_name_lookup[v_name.lower()] = v_name
            
        for e in spec.Events:
            e_id = str(e.CEID)
            e_name = e.EventName
            
            entity_id_lookup[e_id] = e_id
            if e_name: entity_id_lookup[e_name.lower()] = e_id
            
            entity_name_lookup[e_id] = e_name
            if e_name: entity_name_lookup[e_name.lower()] = e_name
            
        for a in spec.Alarms:
            a_id = str(a.AlarmID)
            a_name = a.AlarmName
            
            entity_id_lookup[a_id] = a_id
            if a_name: entity_id_lookup[a_name.lower()] = a_id
            
            entity_name_lookup[a_id] = a_name
            if a_name: entity_name_lookup[a_name.lower()] = a_name

        valid_tag_ids = {t.tag_id for t in target_tags}

        valid_suggestions = []
        for s in data.get("Suggestions", []):
            eq_field_raw = str(s.get("EquipmentFieldName", "")).lower()
            if eq_field_raw in entity_id_lookup and eq_field_raw in entity_name_lookup:
                s["EquipmentID"] = entity_id_lookup[eq_field_raw]
                s["EquipmentFieldName"] = entity_name_lookup[eq_field_raw] or entity_id_lookup[eq_field_raw]
            else:
                continue
                
            if (
                s.get("MESField") in valid_tag_ids
                and s.get("Confidence", 0) >= 0.1
            ):
                tag_id = s.get("MESField")
                valid_suggestions.append(s)

        data["Suggestions"] = valid_suggestions
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
Each mapping should include the `EquipmentFieldName` (instead of EntityID), the `EntityType` (variable, event, or alarm), the `MESField` (instead of TagID), a `Confidence` score (0.0 to 1.0), and a brief `Reasoning`.

GUIDELINES:
1. Make best-effort, fuzzy matches between specialized equipment events/alarms and generic MES Tags (e.g. 'BeamIgnited' or 'ImplantStarted' -> 'LotStart' or 'TrackIn').
2. Only leave an entity unmapped if it is completely irrelevant. Confidence can be as low as 0.1 for fuzzy matches.
3. Relax data type matching if they are logically compatible.
4. Do not invent or hallucinate IDs. Only use exact IDs provided in the lists above.

JSON SCHEMA:
{schema}

TOOL ID: {spec.ToolID}

Only output the JSON object. No prose.
"""
