"""
Equipment spec extractor — receives its LLM strategy via constructor injection.
No longer self-creates its dependencies; the ServiceContainer provides them.
"""
import json
import logging

from app.schemas.secsgem import EquipmentSpec
from app.utils.llm_factory import LLMStrategy
from pydantic import ValidationError

logger = logging.getLogger(__name__)


class EquipmentExtractor:
    """Extracts a structured EquipmentSpec from raw PDF text using an LLM."""

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        # Dependencies injected — no hard-wired provider choice here.
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize(data: dict) -> None:
        """Drop state transitions with null from/to_state to avoid validation failures."""
        transitions = data.get("state_transitions") or []
        data["state_transitions"] = [
            t for t in transitions if t.get("from_state") and t.get("to_state")
        ]

    def _build_prompt(self, pdf_text: str) -> str:
        return f"""You extract semiconductor equipment SECS/GEM specs from technical documentation.

Output a single JSON object that conforms to this structure. No prose, no markdown fences, no commentary.
CRITICAL: DO NOT output the schema itself. You must output a JSON object populated with the actual extracted data.

EXPECTED JSON FORMAT:
{{
  "tool_id": "string",
  "tool_type": "string",
  "model": "string (optional)",
  "protocol": "SECS/GEM",
  "connection": {{"host": "string", "port": 123, "mode": "string"}},
  "variables": [
    {{
      "vid": "string",
      "name": "string",
      "type": "float|integer|string|boolean",
      "unit": "string",
      "category": "SV|DV",
      "access": "read|write|read/write",
      "description": "string",
      "confidence": 0.0 to 1.0
    }}
  ],
  "events": [
    {{
      "ceid": "string",
      "name": "string",
      "description": "string",
      "linked_vids": ["string"],
      "report": true,
      "confidence": 0.0 to 1.0
    }}
  ],
  "alarms": [
    {{
      "alarm_id": "string",
      "name": "string",
      "severity": "critical|warning|info",
      "linked_vid": "string",
      "description": "string",
      "confidence": 0.0 to 1.0
    }}
  ],
  "remote_commands": [
    {{
      "rcmd": "string",
      "description": "string",
      "parameters": [{{"name": "string", "type": "string"}}],
      "confidence": 0.0 to 1.0
    }}
  ],
  "states": [
    {{"state_id": "string", "name": "string", "description": "string"}}
  ],
  "state_transitions": [
    {{
      "from_state": "string",
      "to_state": "string",
      "trigger_event": "string",
      "trigger_command": "string",
      "manual": false
    }}
  ]
}}

CONFIDENCE RUBRIC (set the `confidence` field per-entity):
- 1.0  = verbatim from a clearly labeled table
- 0.7  = inferred from prose with a clear section heading or strong signal
- <0.5 = guessed from weak context

HARD RULES:
- Populate `Event.linked_vids` from any "Linked VIDs" column or comma-separated VID list following an event description.
- Populate `state_transitions` from text matching `<State> -> <State> (Triggered by <event/command>)` patterns.
  - `from_state` and `to_state` are REQUIRED, must be non-null state names matching entries in `states`.
  - If the trigger is an event, set `trigger_event` (the event name) and leave `trigger_command` null.
  - If the trigger is a command, set `trigger_command` (the RCMD name) and leave `trigger_event` null.
  - If the transition is described as "manual" with no event/command, set `manual: true` and leave both trigger fields null.
  - Never set both `trigger_event` and `trigger_command`.
- `Alarm.severity` MUST be lowercase: `critical`, `warning`, or `info`.
- If a section is absent from the document, return an empty list. Do NOT invent IDs, names, or fields.
- Output a single JSON object that validates against the schema above. Nothing else.

### DOCUMENT
{pdf_text}
"""
