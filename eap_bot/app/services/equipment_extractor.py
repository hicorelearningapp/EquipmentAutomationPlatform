import json
import logging

from app.schemas.secsgem import EquipmentSpec
from app.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)


class EquipmentExtractor:

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)

    def extract(self, pdf_text: str) -> EquipmentSpec:
        prompt = self._build_prompt(pdf_text)
        raw = self._llm.invoke(prompt).content
        try:
            data = json.loads(raw)
            if "$defs" in data:
                raise ValueError(
                    "You output the JSON schema itself instead of the extracted data."
                )
            self._sanitize(data)
            return EquipmentSpec.model_validate(data)
        except Exception as e:
            error_msg = str(e)
            logger.warning("Primary extraction failed (%s) — retrying with correction prompt.", error_msg)
            retry_prompt = (
                prompt
                + f"\n\nCRITICAL ERROR IN PREVIOUS ATTEMPT:\n{error_msg}\n\n"
                "You MUST output a valid JSON object populated with the actual data "
                "from the document. DO NOT output the JSON schema definitions (e.g. '$defs')."
            )
            raw = self._llm_retry.invoke(retry_prompt).content
            data = json.loads(raw)
            if "$defs" in data:
                raise ValueError("Model persistently returned the schema instead of the data.")
            self._sanitize(data)
            return EquipmentSpec.model_validate(data)

    @staticmethod
    def _sanitize(data: dict) -> None:
        transitions = data.get("StateTransitions") or data.get("state_transitions") or []
        data["StateTransitions"] = [
            t for t in transitions if (t.get("FromState") or t.get("from_state")) and (t.get("ToState") or t.get("to_state"))
        ]

    def _build_prompt(self, pdf_text: str) -> str:
        return f"""You extract semiconductor equipment SECS/GEM specs from technical documentation.

Output a single JSON object that conforms to this structure. No prose, no markdown fences, no commentary.
CRITICAL: DO NOT output the schema itself. You must output a JSON object populated with the actual extracted data.

EXPECTED JSON FORMAT:
{{
  "ToolID": "string",
  "ToolType": "string",
  "Model": "string (optional)",
  "Protocol": "SECS/GEM",
  "Connection": {{"Host": "string", "Port": 123, "Mode": "string"}},
  "Variables": [
    {{
      "VID": 123,
      "Name": "string",
      "Type": "float|integer|string|boolean",
      "Unit": "string",
      "Category": "SV|DV",
      "Access": "read|write|read/write",
      "Description": "string",
      "Confidence": 0.0 to 1.0
    }}
  ],
  "Events": [
    {{
      "CEID": 123,
      "Name": "string",
      "Description": "string",
      "LinkedVIDs": [123],
      "Report": true,
      "Confidence": 0.0 to 1.0
    }}
  ],
  "Alarms": [
    {{
      "AlarmID": 123,
      "Name": "string",
      "Severity": "critical|warning|info",
      "LinkedVID": 123,
      "Description": "string",
      "Confidence": 0.0 to 1.0
    }}
  ],
  "RemoteCommands": [
    {{
      "RCMD": "string",
      "Description": "string",
      "Parameters": [{{ "Name": "string", "Type": "string" }}],
      "Confidence": 0.0 to 1.0
    }}
  ],
  "States": [
    {{ "StateID": "string", "Name": "string", "Description": "string" }}
  ],
  "StateTransitions": [
    {{
      "FromState": "string",
      "ToState": "string",
      "TriggerEvent": "string",
      "TriggerCommand": "string",
      "Manual": false
    }}
  ]
}}

CONFIDENCE RUBRIC (set the `Confidence` field per-entity):
- 1.0  = verbatim from a clearly labeled table
- 0.7  = inferred from prose with a clear section heading or strong signal
- <0.5 = guessed from weak context

HARD RULES:
- Populate `LinkedVIDs` from any "Linked VIDs" column or comma-separated VID list following an event description.
- Populate `StateTransitions` from text matching `<State> -> <State> (Triggered by <event/command>)` patterns.
  - `FromState` and `ToState` are REQUIRED, must be non-null state names matching entries in `States`.
  - If the trigger is an event, set `TriggerEvent` (the event name) and leave `TriggerCommand` null.
  - If the trigger is a command, set `TriggerCommand` (the RCMD name) and leave `TriggerEvent` null.
  - If the transition is described as "manual" with no event/command, set `Manual: true` and leave both trigger fields null.
  - Never set both `TriggerEvent` and `TriggerCommand`.
- `Severity` MUST be lowercase: `critical`, `warning`, or `info`.
- If a section is absent from the document, return an empty list. Do NOT invent IDs, names, or fields.
- Output a single JSON object that validates against the schema above. Nothing else.

### DOCUMENT
{{pdf_text}}
"""
