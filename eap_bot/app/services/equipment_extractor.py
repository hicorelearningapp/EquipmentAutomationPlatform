import json
import logging
from typing import Optional

from app.schemas.secsgem import EquipmentSpec
from app.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)


class EquipmentExtractor:
    """Extracts SECS/GEM equipment specifications from PDF text.

    Uses a Map-Reduce strategy for large documents:
      1. Split the text into token-safe chunks.
      2. Extract a partial EquipmentSpec from each chunk (Map).
      3. Merge all partial specs into one, deduplicating by ID (Reduce).

    Small documents that fit within a single chunk bypass the
    chunking/merging entirely for zero overhead.
    """

    MAX_CHUNK_CHARS = 8000
    CHUNK_OVERLAP = 200

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pdf_text: str) -> EquipmentSpec:
        """Extract an EquipmentSpec from the full document text.

        Automatically chunks large documents to stay within LLM token limits.
        """
        chunks = self._chunk_text(pdf_text)

        if len(chunks) == 1:
            return self._extract_chunk(chunks[0], chunk_num=1, total_chunks=1)

        logger.info("Document split into %d chunks for extraction.", len(chunks))

        partial_specs: list[EquipmentSpec] = []
        for i, chunk in enumerate(chunks, 1):
            logger.info("Extracting chunk %d/%d ...", i, len(chunks))
            spec = self._extract_chunk(chunk, chunk_num=i, total_chunks=len(chunks))
            partial_specs.append(spec)

        merged = self._merge_specs(partial_specs)
        logger.info(
            "Merged %d chunks → %d SVs, %d DVs, %d Events, %d Alarms, %d RCMDs",
            len(chunks),
            len(merged.StatusVariables),
            len(merged.DataVariables),
            len(merged.Events),
            len(merged.Alarms),
            len(merged.RemoteCommands),
        )
        return merged

    # ------------------------------------------------------------------
    # Chunking (Split)
    # ------------------------------------------------------------------

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks, preferring section boundaries."""
        max_chars = self.MAX_CHUNK_CHARS
        overlap = self.CHUNK_OVERLAP

        if len(text) <= max_chars:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + max_chars

            if end >= len(text):
                chunks.append(text[start:])
                break

            # Find a clean break point within the slice
            slice_ = text[start:end]
            for sep in ["\n\n", "\n", " "]:
                idx = slice_.rfind(sep)
                if idx > max_chars // 2:
                    end = start + idx + len(sep)
                    break

            chunks.append(text[start:end])
            start = end - overlap

        return chunks

    # ------------------------------------------------------------------
    # Per-Chunk Extraction (Map)
    # ------------------------------------------------------------------

    def _extract_chunk(self, chunk: str, chunk_num: int, total_chunks: int) -> EquipmentSpec:
        """Extract from a single chunk. Returns an empty spec on failure."""
        if total_chunks > 1:
            preamble = (
                f"This is section {chunk_num} of {total_chunks} from a larger document. "
                "Extract ONLY the SECS/GEM data present in THIS section. "
                "Return empty lists for any categories not found in this section.\n\n"
            )
        else:
            preamble = ""

        prompt = self._build_prompt(preamble + chunk)
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
            logger.warning(
                "Primary extraction failed for chunk %d/%d (%s) — retrying.",
                chunk_num, total_chunks, error_msg,
            )
            retry_prompt = (
                prompt
                + f"\n\nCRITICAL ERROR IN PREVIOUS ATTEMPT:\n{error_msg}\n\n"
                "You MUST output a valid JSON object populated with the actual data "
                "from the document. DO NOT output the JSON schema definitions (e.g. '$defs')."
            )
            try:
                raw = self._llm_retry.invoke(retry_prompt).content
                data = json.loads(raw)
                if "$defs" in data:
                    raise ValueError("Model persistently returned the schema instead of the data.")
                self._sanitize(data)
                return EquipmentSpec.model_validate(data)
            except Exception as retry_err:
                if total_chunks == 1:
                    raise  # Single-chunk doc: propagate the error
                logger.error(
                    "Chunk %d/%d failed after retry (%s). Returning empty spec for this chunk.",
                    chunk_num, total_chunks, retry_err,
                )
                return EquipmentSpec(ToolID="", ToolType="")

    # ------------------------------------------------------------------
    # Merging (Reduce)
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_specs(specs: list[EquipmentSpec]) -> EquipmentSpec:
        """Merge multiple partial specs into one, deduplicating by ID.

        For items with the same ID, the entry with higher Confidence wins.
        Scalar fields (ToolID, ToolType, etc.) take the first non-empty value.
        """
        merged = EquipmentSpec(ToolID="", ToolType="")

        # Scalar fields: first non-empty value wins
        for spec in specs:
            if not merged.DocumentType and spec.DocumentType:
                merged.DocumentType = spec.DocumentType
            if not merged.ToolID and spec.ToolID:
                merged.ToolID = spec.ToolID
            if not merged.ToolType and spec.ToolType:
                merged.ToolType = spec.ToolType
            if not merged.Model and spec.Model:
                merged.Model = spec.Model

        # List fields: concatenate then deduplicate
        merged.StatusVariables = EquipmentExtractor._dedup_by_key(
            [sv for s in specs for sv in s.StatusVariables], key="SVID"
        )
        merged.DataVariables = EquipmentExtractor._dedup_by_key(
            [dv for s in specs for dv in s.DataVariables], key="DvID"
        )
        merged.Events = EquipmentExtractor._dedup_by_key(
            [ev for s in specs for ev in s.Events], key="CEID"
        )
        merged.Alarms = EquipmentExtractor._dedup_by_key(
            [al for s in specs for al in s.Alarms], key="AlarmID"
        )
        merged.RemoteCommands = EquipmentExtractor._dedup_by_key(
            [rc for s in specs for rc in s.RemoteCommands], key="RCMD"
        )
        merged.States = EquipmentExtractor._dedup_by_key(
            [st for s in specs for st in s.States], key="StateID"
        )
        merged.StateTransitions = EquipmentExtractor._dedup_transitions(
            [tr for s in specs for tr in s.StateTransitions]
        )

        return merged

    @staticmethod
    def _dedup_by_key(items: list, key: str) -> list:
        """Keep only the highest-confidence entry per unique key value.

        Items without a Confidence attribute are treated as confidence=1.0.
        """
        best: dict = {}
        for item in items:
            id_val = getattr(item, key)
            confidence = getattr(item, "Confidence", 1.0)
            if id_val not in best or confidence > getattr(best[id_val], "Confidence", 1.0):
                best[id_val] = item
        return list(best.values())

    @staticmethod
    def _dedup_transitions(transitions: list) -> list:
        """Deduplicate state transitions by (FromState, ToState) tuple."""
        seen: dict[tuple[str, str], object] = {}
        for tr in transitions:
            key = (tr.FromState, tr.ToState)
            if key not in seen:
                seen[key] = tr
        return list(seen.values())

    # ------------------------------------------------------------------
    # Sanitization
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize(data: dict) -> None:
        """Clean up malformed transition entries before validation."""
        transitions = data.get("StateTransitions") or data.get("state_transitions") or []
        data["StateTransitions"] = [
            t for t in transitions
            if (t.get("FromState") or t.get("from_state"))
            and (t.get("ToState") or t.get("to_state"))
        ]

    # ------------------------------------------------------------------
    # Prompt Builder
    # ------------------------------------------------------------------

    def _build_prompt(self, pdf_text: str) -> str:
        return f"""You extract semiconductor equipment SECS/GEM specs from technical documentation.

Output a single JSON object that conforms to this structure. No prose, no markdown fences, no commentary.
CRITICAL: DO NOT output the schema itself. You must output a JSON object populated with the actual extracted data.

EXPECTED JSON FORMAT:
{{
  "DocumentType": "string (User Manuals|Troubleshooting Guidance|GEM Manual|Variable Files)",
  "ToolID": "string",
  "ToolType": "string",
  "Model": "string (optional)",
  "Protocol": "SECS/GEM",
  "StatusVariable":[
    {{
      "SVID": 123,
      "Name": "string",
      "Description": "string",
      "DataType": "string",
      "AccessType": "string",
      "Value": "string",
      "Confidence": 0.0 to 1.0 (double)
    }}
  ],
  "DataVariable": [
    {{
      "DvID": 123,
      "Name": "string",
      "ValueType": "string (float|integer|string|boolean)",
      "Unit": "string",
      "Confidence": 0.0 to 1.0 (double)
    }}
  ],
  "Events": [
    {{
      "CEID": 123,
      "Name": "string",
      "Description": "string",
      "LinkedVIDs": [123],
      "ReportID": "string",
      "Confidence": 0.0 to 1.0 (double)
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
- For every Event, you MUST extract the ReportID and the LinkedVIDs (Variables) associated with that report. If the document does not specify a ReportID, you MUST suggest a logical one (e.g. "RPT_{{CEID}}"). Do not leave it null.
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
{pdf_text}
"""
