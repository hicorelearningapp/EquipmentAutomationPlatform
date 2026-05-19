import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Union

import pdfplumber
import tiktoken

from app.config import settings
from app.schemas.secsgem import (
    Alarm,
    DataVariable,
    EquipmentSpec,
    Event,
    RemoteCommand,
    RCMDParameter,
    State,
    StateTransition,
    StatusVariable,
)
from app.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)


class EquipmentExtractor:
    """Extracts SECS/GEM equipment specifications from PDF text.

    Uses a Map-Reduce strategy for large documents:
      1. Split the text into token-sized chunks.
      2. Extract a partial EquipmentSpec from each chunk in parallel (Map).
      3. Merge all partial specs into one, deduplicating by ID (Reduce).

    Small documents that fit within a single chunk bypass the
    chunking/merging entirely for zero overhead.
    """

    # cl100k_base is the OpenAI tokenizer; close enough to Llama tokenization
    # for chunking decisions (within ~10%). Avoids a heavier transformers dep.
    _ENCODER_NAME = "cl100k_base"

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)
        self._encoder = tiktoken.get_encoding(self._ENCODER_NAME)
        self._chunk_tokens = settings.EXTRACTOR_CHUNK_TOKENS
        self._chunk_overlap_tokens = settings.EXTRACTOR_CHUNK_OVERLAP_TOKENS
        self._max_parallel = settings.EXTRACTOR_MAX_PARALLEL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self, pdf_text: str) -> EquipmentSpec:
        """Extract an EquipmentSpec from the full document text.

        Automatically chunks large documents and extracts chunks in parallel.
        """
        chunks = self._chunk_text(pdf_text)

        if len(chunks) == 1:
            return self._extract_chunk(chunks[0], chunk_num=1, total_chunks=1)

        workers = min(self._max_parallel, len(chunks))
        logger.info(
            "Document split into %d chunks; extracting up to %d in parallel.",
            len(chunks), workers,
        )

        partial_specs: list[EquipmentSpec] = [None] * len(chunks)  # type: ignore[list-item]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._extract_chunk, chunk, i + 1, len(chunks)): i
                for i, chunk in enumerate(chunks)
            }
            for future in futures:
                idx = futures[future]
                partial_specs[idx] = future.result()

        merged = self._merge_specs(partial_specs)
        logger.info(
            "Merged %d chunks - %d SVs, %d DVs, %d Events, %d Alarms, %d RCMDs",
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
        """Split text into overlapping token-sized chunks."""
        tokens = self._encoder.encode(text)

        if len(tokens) <= self._chunk_tokens:
            return [text]

        chunks: list[str] = []
        start = 0
        stride = self._chunk_tokens - self._chunk_overlap_tokens

        while start < len(tokens):
            end = start + self._chunk_tokens
            chunk_tokens = tokens[start:end]
            chunks.append(self._encoder.decode(chunk_tokens))
            if end >= len(tokens):
                break
            start += stride

        return chunks

    # ------------------------------------------------------------------
    # Per-Chunk Extraction (Map)
    # ------------------------------------------------------------------

    def _extract_chunk(self, chunk: str, chunk_num: int, total_chunks: int) -> EquipmentSpec:
        """Extract from a single chunk. Returns an empty spec on failure in multi-chunk mode."""
        if total_chunks > 1:
            preamble = (
                f"This is section {chunk_num} of {total_chunks} from a larger document. "
                "Extract ONLY the SECS/GEM data present in THIS section. "
                "Return empty lists for any categories not found in this section.\n\n"
            )
        else:
            preamble = ""

        prompt = self._build_prompt(preamble + chunk)

        try:
            raw = self._llm.invoke(prompt).content
            if isinstance(raw, list):
                raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
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
                "Primary extraction failed for chunk %d/%d (%s) - retrying.",
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
                if isinstance(raw, list):
                    raw = "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in raw)
                data = json.loads(raw)
                if "$defs" in data:
                    raise ValueError("Model persistently returned the schema instead of the data.")
                self._sanitize(data)
                return EquipmentSpec.model_validate(data)
            except Exception as retry_err:
                if total_chunks == 1:
                    raise
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

        for spec in specs:
            if not merged.DocumentType and spec.DocumentType:
                merged.DocumentType = spec.DocumentType
            if not merged.ToolID and spec.ToolID:
                merged.ToolID = spec.ToolID
            if not merged.ToolType and spec.ToolType:
                merged.ToolType = spec.ToolType
            if not merged.Model and spec.Model:
                merged.Model = spec.Model

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
        """Keep only the highest-confidence entry per unique key value."""
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
      "RCMD": "string - the name of the command/message",
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


# ── Tunables ─────────────────────────────────────────────────────────────────

# If we classify fewer than this many tables, signal the caller to fall back.
MIN_CLASSIFIED_TABLES = 1

# Maximum number of table rows sent to the LLM in one call (avoids huge prompts).
MAX_ROWS_PER_PROMPT = 300

# ── Keyword sets for rule-based table classification ─────────────────────────
# Keys match EquipmentSpec field names.  Each set contains lowercase substrings
# that, if found in ANY header cell, identify the table section.

_SECTION_KEYWORDS: dict[str, set[str]] = {
    "StatusVariables": {
        "svid", "sv id", "status variable", "statusvariable",
        "variable id", "variable name", "access type",
    },
    "DataVariables": {
        "dvid", "dv id", "data variable", "datavariable",
        "value type", "valuetype",
    },
    "Events": {
        "ceid", "ce id", "collection event", "collectionevent",
        "event id", "event name",
    },
    "Alarms": {
        "alarm id", "alarmid", "alarm name", "alarm text",
        "alarm code", "alid", "al id", "severity",
    },
    "RemoteCommands": {
        "rcmd", "remote command", "remotecommand", "command name",
        "command id",
    },
    "States": {
        "state id", "stateid", "state name", "equipment state",
    },
    "StateTransitions": {
        "from state", "to state", "fromstate", "tostate",
        "transition", "trigger",
    },
}

# ── Per-section LLM prompts ───────────────────────────────────────────────────

_PROMPTS: dict[str, str] = {
    "StatusVariables": """You are a SECS/GEM integration expert.
Below is a table extracted from a semiconductor equipment manual.
Convert every row into a JSON array of StatusVariable objects.

Each object MUST have:
  "svid"        : integer  — the Status Variable ID
  "name"        : string   — variable name
  "description" : string   — description (empty string if not present)
  "data_type"   : string   — e.g. "U4", "ASCII", "BOOLEAN"
  "access_type" : string   — e.g. "RO", "RW"
  "value"       : string   — default or example value (empty string if not present)
  "confidence"  : float    — 1.0 if ID and name are clearly present, else 0.7

Return ONLY a JSON object: {{"StatusVariable": [...]}}
No prose, no markdown fences.

TABLE:
{table}
""",

    "DataVariables": """You are a SECS/GEM integration expert.
Below is a table extracted from a semiconductor equipment manual.
Convert every row into a JSON array of DataVariable objects.

Each object MUST have:
  "dvid"       : integer — the Data Variable ID
  "name"       : string  — variable name
  "value_type" : string  — e.g. "float", "integer", "string", "boolean"
  "unit"       : string  — unit of measurement (empty string if not present)
  "confidence" : float   — 1.0 if ID and name are clearly present, else 0.7

Return ONLY a JSON object: {{"DataVariable": [...]}}
No prose, no markdown fences.

TABLE:
{table}
""",

    "Events": """You are a SECS/GEM integration expert.
Below is a table extracted from a semiconductor equipment manual.
Convert every row into a JSON array of Collection Event objects.

Each object MUST have:
  "ceid"        : integer    — the Collection Event ID
  "name"        : string     — event name
  "description" : string     — description (empty string if not present)
  "linked_vids" : [integer]  — list of linked VIDs (empty list if not present)
  "report_id"   : string     — report ID if mentioned, else null
  "report"      : boolean    — true (default)
  "confidence"  : float      — 1.0 if ID and name are clearly present, else 0.7

Return ONLY a JSON object: {{"events": [...]}}
No prose, no markdown fences.

TABLE:
{table}
""",

    "Alarms": """You are a SECS/GEM integration expert.
Below is a table extracted from a semiconductor equipment manual.
Convert every row into a JSON array of Alarm objects.

Each object MUST have:
  "alarm_id"    : integer — the Alarm ID
  "name"        : string  — alarm name or alarm text
  "severity"    : string  — must be exactly one of: "critical", "warning", "info"
  "linked_vid"  : integer — linked VID if present, else null
  "description" : string  — description (empty string if not present)
  "confidence"  : float   — 1.0 if ID and name are clearly present, else 0.7

Return ONLY a JSON object: {{"alarms": [...]}}
No prose, no markdown fences.

TABLE:
{table}
""",

    "RemoteCommands": """You are a SECS/GEM integration expert.
Below is a table extracted from a semiconductor equipment manual.
Convert every row into a JSON array of RemoteCommand objects.

Each object MUST have:
  "rcmd"        : string — the command name/identifier
  "description" : string — description (empty string if not present)
  "parameters"  : list   — list of {{"name": string, "type": string}} objects (empty list if none)
  "confidence"  : float  — 1.0 if command name is clearly present, else 0.7

Return ONLY a JSON object: {{"remote_commands": [...]}}
No prose, no markdown fences.

TABLE:
{table}
""",

    "States": """You are a SECS/GEM integration expert.
Below is a table extracted from a semiconductor equipment manual.
Convert every row into a JSON array of State objects.

Each object MUST have:
  "state_id"    : string — state identifier
  "name"        : string — state name
  "description" : string — description (empty string if not present)

Return ONLY a JSON object: {{"states": [...]}}
No prose, no markdown fences.

TABLE:
{table}
""",

    "StateTransitions": """You are a SECS/GEM integration expert.
Below is a table extracted from a semiconductor equipment manual.
Convert every row into a JSON array of StateTransition objects.

Each object MUST have:
  "from_state"      : string  — source state name (REQUIRED, must not be null)
  "to_state"        : string  — target state name (REQUIRED, must not be null)
  "trigger_event"   : string  — triggering event name, or null if none
  "trigger_command" : string  — triggering command name, or null if none
  "manual"          : boolean — true if the transition is manual with no event/command trigger

Rules:
- Never set both trigger_event and trigger_command on the same entry.
- If neither event nor command triggers the transition, set manual: true.

Return ONLY a JSON object: {{"state_transitions": [...]}}
No prose, no markdown fences.

TABLE:
{table}
""",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_rows(raw_table: list[list]) -> list[list[str]]:
    """Remove completely empty rows; coerce every cell to a stripped string."""
    result = []
    for row in raw_table:
        cleaned = [str(cell).strip() if cell is not None else "" for cell in row]
        if any(c for c in cleaned):          # skip fully-empty rows
            result.append(cleaned)
    return result


def _table_to_text(rows: list[list[str]]) -> str:
    """Serialise rows to a pipe-delimited markdown table string."""
    if not rows:
        return ""
    col_widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))]
    lines = []
    for idx, row in enumerate(rows):
        padded = [row[i].ljust(col_widths[i]) for i in range(len(row))]
        lines.append("| " + " | ".join(padded) + " |")
        if idx == 0:
            lines.append("|" + "|".join("-" * (w + 2) for w in col_widths) + "|")
    return "\n".join(lines)


def _classify_table(rows: list[list[str]]) -> str | None:
    """
    Return the EquipmentSpec field name (e.g. 'StatusVariables') that best
    matches the table header row, or None if no match is found.

    We look at the first non-empty row (assumed to be the header).
    """
    if not rows:
        return None

    header_text = " ".join(rows[0]).lower()

    best_section: str | None = None
    best_hits = 0

    for section, keywords in _SECTION_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in header_text)
        if hits > best_hits:
            best_hits = hits
            best_section = section

    return best_section if best_hits > 0 else None


def _safe_int(val: object) -> int | None:
    """Try to parse an integer from a value that might be a string."""
    try:
        return int(str(val).strip().split()[0])   # handle "123 (decimal)" etc.
    except (ValueError, TypeError, IndexError):
        return None


# ── Main class ────────────────────────────────────────────────────────────────

class TableAwareExtractor:
    """
    Extracts SECS/GEM specs by locating and converting structured tables in the
    PDF, rather than chunking raw text.

    Usage
    -----
        extractor = TableAwareExtractor(llm_strategy)
        spec, ok = extractor.extract(pdf_path)
        if not ok:
            spec = fallback_text_extractor.extract(plain_text)
    """

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def extract(self, pdf_path: Union[str, Path]) -> tuple[EquipmentSpec, bool]:
        """
        Returns (spec, success).

        success=False signals the caller that no tables were found / classified
        and it should fall back to the text-chunking extractor.
        """
        pdf_path = Path(pdf_path)
        all_tables = self._extract_tables_from_pdf(pdf_path)

        if not all_tables:
            logger.info("TableAwareExtractor: no tables found in %s — signalling fallback", pdf_path.name)
            return EquipmentSpec(ToolID="", ToolType=""), False

        # Classify and group tables by section
        classified: dict[str, list[list[list[str]]]] = {}
        unclassified_count = 0

        for rows in all_tables:
            section = _classify_table(rows)
            if section:
                classified.setdefault(section, []).append(rows)
                logger.debug("TableAwareExtractor: table with %d rows → %s", len(rows), section)
            else:
                unclassified_count += 1

        logger.info(
            "TableAwareExtractor: %d tables found, %d classified across %d sections, %d unclassified",
            len(all_tables), sum(len(v) for v in classified.values()),
            len(classified), unclassified_count,
        )

        if len(classified) < MIN_CLASSIFIED_TABLES:
            logger.info("TableAwareExtractor: too few classified tables — signalling fallback")
            return EquipmentSpec(ToolID="", ToolType=""), False

        # Extract each section and merge
        partial_specs: list[EquipmentSpec] = []
        for section, table_list in classified.items():
            for idx, rows in enumerate(table_list):
                partial = self._extract_section(section, rows, idx + 1, len(table_list))
                if partial:
                    partial_specs.append(partial)

        if not partial_specs:
            return EquipmentSpec(ToolID="", ToolType=""), False

        merged = self._merge_specs(partial_specs)
        logger.info(
            "TableAwareExtractor: merged → %d SVs, %d DVs, %d Events, %d Alarms, %d RCMDs",
            len(merged.StatusVariables), len(merged.DataVariables),
            len(merged.Events), len(merged.Alarms), len(merged.RemoteCommands),
        )
        return merged, True

    # ── PDF table extraction ──────────────────────────────────────────────────

    @staticmethod
    def _extract_tables_from_pdf(pdf_path: Path) -> list[list[list[str]]]:
        """Return all non-empty tables from the PDF as cleaned row lists."""
        result: list[list[list[str]]] = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    raw_tables = page.extract_tables()
                    if not raw_tables:
                        continue
                    for raw in raw_tables:
                        cleaned = _clean_rows(raw)
                        if len(cleaned) >= 2:          # need at least header + 1 data row
                            result.append(cleaned)
        except Exception as exc:
            logger.error("TableAwareExtractor: pdfplumber failed on %s: %s", pdf_path.name, exc)
        return result

    # ── Per-section LLM call ──────────────────────────────────────────────────

    def _extract_section(
        self,
        section: str,
        rows: list[list[str]],
        table_idx: int,
        total_tables: int,
    ) -> EquipmentSpec | None:
        """Send one table to the LLM and parse the returned JSON into an EquipmentSpec."""
        prompt_template = _PROMPTS.get(section)
        if not prompt_template:
            return None

        # Truncate very large tables to avoid exceeding context limits
        if len(rows) > MAX_ROWS_PER_PROMPT:
            logger.warning(
                "TableAwareExtractor: truncating %s table %d/%d from %d to %d rows",
                section, table_idx, total_tables, len(rows), MAX_ROWS_PER_PROMPT,
            )
            rows = rows[:1] + rows[1: MAX_ROWS_PER_PROMPT]  # always keep the header

        table_text = _table_to_text(rows)
        prompt = prompt_template.format(table=table_text)

        raw = self._call_llm(prompt, section, table_idx, total_tables)
        if raw is None:
            return None

        return self._parse_response(raw, section)

    def _call_llm(
        self, prompt: str, section: str, table_idx: int, total: int
    ) -> str | None:
        """Call the LLM with one retry on failure. Returns raw response text or None."""
        try:
            response = self._llm.invoke(prompt)
            raw = response.content
            if isinstance(raw, list):
                raw = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw
                )
            return raw
        except Exception as exc:
            logger.warning(
                "TableAwareExtractor: primary LLM call failed for %s table %d/%d (%s) — retrying",
                section, table_idx, total, exc,
            )

        try:
            response = self._llm_retry.invoke(prompt)
            raw = response.content
            if isinstance(raw, list):
                raw = "".join(
                    part.get("text", "") if isinstance(part, dict) else str(part)
                    for part in raw
                )
            return raw
        except Exception as exc:
            logger.error(
                "TableAwareExtractor: retry also failed for %s table %d/%d (%s) — skipping",
                section, table_idx, total, exc,
            )
            return None

    # ── Response parsing ──────────────────────────────────────────────────────

    def _parse_response(self, raw: str, section: str) -> EquipmentSpec | None:
        """Parse LLM JSON into a partial EquipmentSpec containing only the relevant list."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("TableAwareExtractor: JSON parse failed for %s: %s", section, exc)
            return None

        spec = EquipmentSpec(ToolID="", ToolType="")

        try:
            if section == "StatusVariables":
                items = data.get("StatusVariable") or data.get("StatusVariables") or []
                spec.StatusVariables = [StatusVariable.model_validate(i) for i in items]

            elif section == "DataVariables":
                items = data.get("DataVariable") or data.get("DataVariables") or []
                spec.DataVariables = [DataVariable.model_validate(i) for i in items]

            elif section == "Events":
                items = data.get("events") or data.get("Events") or []
                spec.Events = [Event.model_validate(i) for i in items]

            elif section == "Alarms":
                items = data.get("alarms") or data.get("Alarms") or []
                spec.Alarms = [Alarm.model_validate(i) for i in items]

            elif section == "RemoteCommands":
                items = data.get("remote_commands") or data.get("RemoteCommands") or []
                spec.RemoteCommands = [RemoteCommand.model_validate(i) for i in items]

            elif section == "States":
                items = data.get("states") or data.get("States") or []
                spec.States = [State.model_validate(i) for i in items]

            elif section == "StateTransitions":
                items = data.get("state_transitions") or data.get("StateTransitions") or []
                valid = [t for t in items if t.get("from_state") and t.get("to_state")]
                spec.StateTransitions = [StateTransition.model_validate(t) for t in valid]

        except Exception as exc:
            logger.warning(
                "TableAwareExtractor: model_validate failed for %s: %s", section, exc
            )
            return None

        return spec

    # ── Merge (same logic as EquipmentExtractor._merge_specs) ─────────────────

    @staticmethod
    def _merge_specs(specs: list[EquipmentSpec]) -> EquipmentSpec:
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

        # Lists: deduplicate by primary ID, highest-confidence wins
        merged.StatusVariables = TableAwareExtractor._dedup_by_key(
            [sv for s in specs for sv in s.StatusVariables], "SVID"
        )
        merged.DataVariables = TableAwareExtractor._dedup_by_key(
            [dv for s in specs for dv in s.DataVariables], "DvID"
        )
        merged.Events = TableAwareExtractor._dedup_by_key(
            [ev for s in specs for ev in s.Events], "CEID"
        )
        merged.Alarms = TableAwareExtractor._dedup_by_key(
            [al for s in specs for al in s.Alarms], "AlarmID"
        )
        merged.RemoteCommands = TableAwareExtractor._dedup_by_key(
            [rc for s in specs for rc in s.RemoteCommands], "RCMD"
        )
        merged.States = TableAwareExtractor._dedup_by_key(
            [st for s in specs for st in s.States], "StateID"
        )
        merged.StateTransitions = TableAwareExtractor._dedup_transitions(
            [tr for s in specs for tr in s.StateTransitions]
        )

        return merged

    @staticmethod
    def _dedup_by_key(items: list, key: str) -> list:
        best: dict = {}
        for item in items:
            id_val = getattr(item, key)
            confidence = getattr(item, "Confidence", 1.0)
            if id_val not in best or confidence > getattr(best[id_val], "Confidence", 1.0):
                best[id_val] = item
        return list(best.values())

    @staticmethod
    def _dedup_transitions(transitions: list) -> list:
        seen: dict[tuple, object] = {}
        for tr in transitions:
            key = (tr.FromState, tr.ToState)
            if key not in seen:
                seen[key] = tr
        return list(seen.values())
