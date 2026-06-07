"""
ReportService
=============
Generates GEM report definitions and event-report links from an already-
extracted EquipmentSpec using a 3-prompt LLM chain.

Chain:
  Step 1 — PDF scan (optional)
      If raw PDF text is provided, ask the LLM to pull out any explicit
      report definitions mentioned in the manual.  This grounds the output
      in real document evidence.

  Step 2 — Report synthesis
      Given the DVs/SVs and any Step-1 hints, generate a list of
      ReportDefinition objects (RPTID, Name, LinkedVIDs).

  Step 3 — CEID linking
      Given the Events and the reports from Step 2, generate the
      links mapping CEIDs to RPTIDs.

All three steps produce JSON.  Failures in any step are logged and result
in an empty list for that step so the caller always gets a valid (possibly
partial) result.
"""

import json
import logging
from typing import Optional

from source.schemas.secsgem import EquipmentSpec, ReportDefinition
from source.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────────

_STEP1_PROMPT = """You are a SECS/GEM integration expert.

Below is an excerpt from a semiconductor equipment manual.
Extract any explicit GEM report definitions you find.
A report definition groups one or more data/status variable IDs (DVIDs or SVIDs)
under a single Report ID (RPTID) that gets sent when a collection event fires.

Return ONLY a JSON object with a "Hints" key containing an array of report definitions.
Each element in the array must have:
  "RPTID"      : string  — the report identifier (e.g. "RPT_001" or as named in the doc)
  "Name"       : string  — a short descriptive name
  "LinkedVIDs" : [int]   — list of DVID/SVID integers associated with this report
  "Type"       : string  — must always be "Built-in"

Example format:
{{
  "Hints": [
    {{ "RPTID": "RPT_1", "Name": "...", "LinkedVIDs": [101, 102], "Type": "Built-in" }}
  ]
}}

If you find no report definitions, return {{"Hints": []}}.
Do not include any explanation or markdown.

Manual excerpt:
{pdf_excerpt}
"""

_STEP2_PROMPT = """You are a SECS/GEM integration expert.

Your task: generate GEM report definitions for the equipment described below.

Equipment has these Data Variables (DVs):
{dvs}

Equipment has these Status Variables (SVs):
{svs}

Existing report hints extracted from the manual (may be empty):
{hints}

Target Events requiring reports (use their LinkedVIDs as items):
{events}

Rules:
- Group related variables into logical reports (e.g. one report per process phase,
  one for alarms, one for recipe data).
- Prefer reusing RPTID values from the hints if they exist; otherwise generate
  sequential IDs like "RPT_001", "RPT_002", etc.
- If you are reusing a report from the hints, preserve its "Type" field (usually "Built-in").
- For any brand new reports you create, set their "Type" field to "Generated".
- Each report should have 2-6 linked variable IDs where possible.
- IMPORTANT: The generated reports must include MORE linked variables than what the CEIDs strictly require. Do not just blindly copy the event's LinkedVIDs. Enrich the reports with additional relevant context variables (such as overall equipment status, process state, control state, or critical alarm states) from the provided DVs and SVs.
- Set "Confidence" between 0.0 and 1.0 based on how certain you are.
- Optionally include a short "Reasoning" string explaining the grouping.

Return ONLY a JSON object with a "Reports" key containing the array of reports.
Each element must have:
  "RPTID"      : string
  "Name"       : string
  "LinkedVIDs" : [int]
  "Type"       : string  ("Built-in" or "Generated")
  "Confidence" : float
  "Reasoning"  : string  (optional)

Do not include any explanation or markdown.
"""



class ReportService:
    _MAX_PDF_EXCERPT = 6000

    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0.0, require_json=True)

    def extract_builtin_reports(self, pdf_text: str = "") -> list[ReportDefinition]:
        hints = self._step1_extract_hints(pdf_text)
        reports = []
        for h in hints:
            try:
                reports.append(ReportDefinition.model_validate(h))
            except Exception as exc:
                logger.warning("Skipping invalid report hint %s: %s", h, exc)
        return reports

    def generate_synthetic_reports(
        self,
        spec: EquipmentSpec,
        hints: list[dict] = None
    ) -> list[ReportDefinition]:
        if hints is None:
            hints = [r.model_dump() for r in spec.Reports]
            
        reports = self._step2_synthesise_reports(spec, hints)
        return reports

    def _step1_extract_hints(self, pdf_text: str) -> list[dict]:
        if not pdf_text.strip():
            return []

        excerpt = pdf_text[: self._MAX_PDF_EXCERPT]
        prompt = _STEP1_PROMPT.format(pdf_excerpt=excerpt)
        try:
            raw = self._invoke(prompt)
            return self._parse_list(raw, step=1)
        except Exception as exc:
            logger.warning("ReportService step 1 failed (non-fatal): %s", exc)
            return []

    def _step2_synthesise_reports(
        self, spec: EquipmentSpec, hints: list[dict]
    ) -> list[ReportDefinition]:
        dvs_text = "\n".join(
            f"  DVID={v.DvID}  Name={v.Name}  Unit={v.Unit or '-'}  Type={v.ValueType}"
            for v in spec.DataVariables
        ) or "  (none)"

        svs_text = "\n".join(
            f"  SVID={v.SVID}  Name={v.Name}  Type={v.DataType}  Access={v.AccessType}"
            for v in spec.StatusVariables
        ) or "  (none)"

        hints_text = json.dumps(hints, indent=2) if hints else "[]"

        events_text = "\n".join(
            f"  CEID={e.CEID}  Name={e.EventName}  LinkedVIDs={e.LinkedVIDs}"
            for e in spec.Events
        ) or "  (none)"

        prompt = _STEP2_PROMPT.format(
            dvs=dvs_text, svs=svs_text, hints=hints_text, events=events_text
        )
        try:
            raw = self._invoke(prompt)
            items = self._parse_list(raw, step=2)
            reports = []
            for item in items:
                try:
                    item["Type"] = "Generated"
                    reports.append(ReportDefinition.model_validate(item))
                except Exception as exc:
                    logger.warning("Skipping invalid report item %s: %s", item, exc)
            logger.info("ReportService step 2: generated %d reports", len(reports))
            return reports
        except Exception as exc:
            logger.error("ReportService step 2 failed: %s", exc)
            return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _invoke(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        response = self._llm.invoke([HumanMessage(content=prompt)])
        content = response.content
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return content.strip()

    @staticmethod
    def _parse_list(raw: str, step: int) -> list[dict]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Strip ```json ... ``` fences
            lines = cleaned.splitlines()
            cleaned = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"ReportService step {step}: LLM returned invalid JSON: {exc}\nRaw: {raw[:300]}"
            ) from exc
        # If it's a dict, find the first key that contains a list (e.g. "Reports", "Links", "Hints")
        if isinstance(result, dict):
            for key in ["Reports", "Links", "Hints", "Data", "LinkedVIDs"]:
                if key in result and isinstance(result[key], list):
                    return result[key]
            # Fallback: take the first value that is a list
            for val in result.values():
                if isinstance(val, list):
                    return val
            raise ValueError(
                f"ReportService step {step}: expected JSON object containing a list, but no list found in: {result.keys()}"
            )

        if not isinstance(result, list):
            raise ValueError(
                f"ReportService step {step}: expected JSON array or object-wrapped array, got {type(result).__name__}"
            )
        return result