import json
import logging
from app.schemas.secsgem import EquipmentSpec
from app.schemas.report import ReportDefinition, EventReportLink, ReportSuggestionResponse
from app.utils.llm_factory import LLMStrategy

logger = logging.getLogger(__name__)

TOOL_CONTEXT = {
    "ETCH":  "Plasma etching tool. Key process variables: RF power, bias voltage, chamber pressure, gas flow. Sequence: pump down → plasma ignition → etch → vent.",
    "CVD":   "Chemical vapor deposition. Key variables: chamber temp, gas flow rates, deposition time, pressure. Sequence: purge → heat → deposit → cool.",
    "LITHO": "Lithography tool. Key variables: focus, dose, stage position, temperature. Sequence: align → expose → develop.",
    "MOCVD": "Metal-organic CVD. Key variables: reactor temp, gas flows, pressure, rotation speed.",
}

class ReportService:
    def __init__(self, llm_strategy: LLMStrategy) -> None:
        self._llm = llm_strategy.get_model(temperature=0, require_json=True)
        self._llm_retry = llm_strategy.get_model(temperature=0.2, require_json=True)

    def suggest_reports(self, spec: EquipmentSpec) -> tuple[list[ReportDefinition], list[EventReportLink]]:
        prompt = self._build_prompt(spec)
        try:
            raw = self._llm.invoke(prompt).content
            data = json.loads(raw)
        except Exception as e:
            logger.warning("Primary report suggestion failed (%s) — retrying.", e)
            raw = self._llm_retry.invoke(prompt).content
            data = json.loads(raw)

        reports = [ReportDefinition.model_validate(r) for r in data.get("reports", [])]
        links = [EventReportLink.model_validate(l) for l in data.get("event_report_links", [])]
        return reports, links

    def _build_prompt(self, spec: EquipmentSpec) -> str:
        tool_context = TOOL_CONTEXT.get(spec.ToolType.upper(), "Semiconductor equipment.")

        svs = [{"svid": v.SVID, "name": v.Name, "description": v.Description or "", "unit": v.Unit or ""} for v in spec.StatusVariables]
        dvs = [{"dvid": v.DvID, "name": v.Name, "description": v.Description or "", "unit": v.Unit or ""} for v in spec.DataVariables]
        events = [{"ceid": e.CEID, "name": e.Name, "description": e.Description or ""} for e in spec.Events]

        return f"""You are a GEM host integration expert. Your task is to design SECS/GEM report definitions and link them to collection events.

TOOL CONTEXT:
  Tool Type: {spec.ToolType}
  Domain: {tool_context}

STATUS VARIABLES (SVIDs):
{json.dumps(svs, indent=2)}

DATA VARIABLES (DVIDs):
{json.dumps(dvs, indent=2)}

COLLECTION EVENTS (CEIDs):
{json.dumps(events, indent=2)}

TASK:
Design report definitions (S2F33) and event-report links (S2F35) following GEM conventions.

RULES:
1. Every event with Report=true MUST have at least one entry in event_report_links.
2. A report contains SVIDs and DVIDs that the MES would logically need when that event fires.
3. RPTIDs must be unique strings. Use format "RPT_{{number}}" (e.g. "RPT_1001").
4. You MAY reuse one report across multiple events if the variable set is identical.
5. Consider two strategies and pick the most appropriate:
   - event_centric: each CEID gets its own dedicated report (cleaner, modern approach)
   - shared: create reusable report groups composed per event (efficient for large tools)
6. Set confidence: 1.0 if variables explicitly mentioned in event description, 0.7 if inferred from event semantics, 0.4 if uncertain.
7. Only use VID numbers that exist in the SVIDs or DVIDs lists above.

OUTPUT (JSON only, no prose):
{{
  "strategy": "event_centric or shared",
  "reports": [
    {{
      "rptid": "RPT_1001",
      "name": "ProcessStartData",
      "linked_vids": [2003, 2006, 3001, 3002],
      "confidence": 0.9,
      "reasoning": "ProcessStart needs recipe, wafer ID, initial chamber state"
    }}
  ],
  "event_report_links": [
    {{
      "ceid": 5001,
      "event_name": "ProcessStarted",
      "rptids": ["RPT_1001"]
    }}
  ]
}}
"""