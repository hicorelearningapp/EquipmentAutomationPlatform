import json
import logging
from typing import List

from app.schemas.mapping import ProjectMapping, VariableMapping
from app.schemas.secsgem import EquipmentSpec
from app.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)

class MappingService:
    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)

    def generate_mapping(self, project_id: str, mes_tags: List[dict], extractions: List[EquipmentSpec]) -> ProjectMapping:
        # 1. Prepare target variables list from all extractions
        target_variables = []
        for spec in extractions:
            for v in spec.variables:
                target_variables.append({
                    "ID": str(v.vid),
                    "Name": v.name,
                    "Description": v.description or "",
                    "Category": v.category  # SV, DV
                })
            for e in spec.events:
                target_variables.append({
                    "ID": str(e.ceid),
                    "Name": e.name,
                    "Description": e.description or "",
                    "Category": "CE"
                })

        # 2. Build and invoke prompt
        prompt = self._build_prompt(mes_tags, target_variables)
        try:
            raw = self._llm.invoke(prompt).content
            data = json.loads(raw)
            mappings_data = data.get("Mappings", [])
            
            final_mappings = []
            for m in mappings_data:
                # Validation through Pydantic (VariableMapping)
                try:
                    final_mappings.append(VariableMapping.model_validate(m))
                except Exception as ve:
                    logger.warning(f"Skipping invalid mapping entry: {ve}")
            
            return ProjectMapping(ProjectID=project_id, Mappings=final_mappings)
            
        except Exception as e:
            logger.error(f"Mapping generation failed: {e}")
            raise

    def _build_prompt(self, mes_tags: List[dict], target_variables: List[dict]) -> str:
        return f"""You are an expert in Semiconductor Equipment Automation (SECS/GEM) and MES integration.
Your task is to map factory MES tags to the available equipment variables (SVIDs) and events (CEIDs).

### INPUT: MES TAGS
{json.dumps(mes_tags, indent=2)}

### TARGET: EQUIPMENT VARIABLES & EVENTS
{json.dumps(target_variables, indent=2)}

### INSTRUCTIONS:
1. For each MES Tag, find the most relevant Equipment Variable or Event.
2. Use semantic similarity between Names and Descriptions.
3. Mapping Rules:
   - If an MES Tag relates to a status, measurement, or value (e.g., 'ChamberPressure', 'Status'), map it to an SVID (Category: SV or DV).
   - If an MES Tag relates to an occurrence, state change, or trigger (e.g., 'ProcessStarted', 'AlarmOccurred'), map it to a CEID (Category: CE).
4. Output the result as a single JSON object with a "Mappings" key.
5. Each mapping MUST use PascalCase keys: MESTag, SVID, CEID, Description.
6. Populate only SVID or CEID per mapping. If mapped to SVID, leave CEID empty.
7. If no confident match is found, leave both SVID and CEID empty.

### EXPECTED JSON FORMAT:
{{
  "Mappings": [
    {{
      "MESTag": "string",
      "SVID": "string",
      "CEID": "string",
      "Description": "string (briefly explain the rationale for this match)"
    }}
  ]
}}

Output ONLY the JSON object. No prose.
"""
