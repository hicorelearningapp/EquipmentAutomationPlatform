import datetime
from dataclasses import dataclass
from typing import List, Dict

from source.schemas.secsgem import EquipmentSpec
from source.schemas.project import DocumentCategory, DocumentMetadata
from source.services.storage_service import StorageService

@dataclass
class ReportDefinition:
    report_id: int
    svids: List[int]
    name: str = ""

@dataclass
class EventLink:
    ceid: int
    report_ids: List[int]
    name: str = ""

class SMLGenerator:
    """Generates the FULL chronological end-to-end SECS/GEM test suite."""
    
    def __init__(self, data_id: int = 1):
        self.data_id = data_id

    # ------------------ PHASE 1: COMM & SETUP ------------------
    def generate_s1f1_ping(self) -> str:
        return "// --- S1F1: Are You There --- \nS1F1 W\n."

    def generate_s1f13_establish_comm(self) -> str:
        return "// --- S1F13: Establish Communication --- \nS1F13 W\n  <L [0]>\n."

    def generate_s1f11_status_variables(self, svids: List[int]) -> str:
        if not svids:
            return "// --- S1F11: Request ALL Status Variables --- \nS1F11 W\n  <L [0]>\n."
        
        lines = [
            "// --- S1F11: Request Specific Status Variables ---",
            "S1F11 W",
            f"  <L [{len(svids)}]"
        ]
        for svid in svids:
            lines.append(f"    <U4 {svid}>")
        lines.append("  >")
        lines.append(".")
        return "\n".join(lines)

    # ------------------ PHASE 2: DATA COLLECTION ------------------
    def generate_s2f33_define_report(self, reports: List[ReportDefinition]) -> str:
        if not reports:
            return ""
        lines = [
            "// --- S2F33: Define Reports ---",
            "S2F33 W",
            f"  <L [2]",
            f"    <U4 {self.data_id}>                    * DATAID",
            f"    <L [{len(reports)}]"
        ]
        for rpt in reports:
            lines.append(f"      <L [2]")
            lines.append(f"        <U4 {rpt.report_id}>                     * RPTID ({rpt.name})")
            lines.append(f"        <L [{len(rpt.svids)}]")
            for svid in rpt.svids:
                lines.append(f"          <U4 {svid}>                 * SVID")
            lines.append("        >")
            lines.append("      >")
            
        lines.append("    >")
        lines.append("  >")
        lines.append(".")
        return "\n".join(lines)

    def generate_s2f35_link_event(self, links: List[EventLink]) -> str:
        if not links:
            return ""
        lines = [
            "// --- S2F35: Link Reports to Events ---",
            "S2F35 W",
            f"  <L [2]",
            f"    <U4 {self.data_id}>                    * DATAID",
            f"    <L [{len(links)}]"
        ]
        for link in links:
            lines.append(f"      <L [2]")
            lines.append(f"        <U4 {link.ceid}>                   * CEID ({link.name})")
            lines.append(f"        <L [{len(link.report_ids)}]")
            for rptid in link.report_ids:
                lines.append(f"          <U4 {rptid}>                   * RPTID")
            lines.append("        >")
            lines.append("      >")
        lines.append("    >")
        lines.append("  >")
        lines.append(".")
        return "\n".join(lines)

    def generate_s2f37_enable_events(self, ceids: List[int]) -> str:
        if not ceids:
            return ""
        lines = [
            "// --- S2F37: Enable Event Reports ---",
            "S2F37 W",
            f"  <Boolean True>                   * CEED",
            f"  <L [{len(ceids)}]"
        ]
        for ceid in ceids:
            lines.append(f"    <U4 {ceid}>                      * CEID")
        lines.append("  >")
        lines.append(".")
        return "\n".join(lines)

    def generate_s2f23_trace_initialize(self, svids: List[int]) -> str:
        if not svids:
            return ""
        lines = [
            "// --- S2F23: Trace Initialize (Every 10s, 100 samples) ---",
            "S2F23 W",
            "  <L [5]",
            "    <U4 1>                       * TRID",
            "    <ASCII \"000010\">             * DSPPER (10s)",
            "    <U4 100>                     * TOTSMP",
            "    <U4 1>                       * REPGSZ",
            f"    <L [{len(svids)}]"
        ]
        for svid in svids:
            lines.append(f"      <U4 {svid}>                    * SVID")
        lines.append("    >")
        lines.append("  >")
        lines.append(".")
        return "\n".join(lines)

    # ------------------ PHASE 3: EQUIPMENT CONTROL ------------------
    def generate_s2f41_host_command(self, rcmd: str, params: Dict[str, str] = None) -> str:
        params = params or {}
        lines = [
            f"// --- S2F41: Host Command ({rcmd}) ---",
            "S2F41 W",
            "  <L [2]",
            f"    <ASCII \"{rcmd}\">",
            f"    <L [{len(params)}]"
        ]
        for cpname, cpval in params.items():
            lines.append("      <L [2]")
            lines.append(f"        <ASCII \"{cpname}\">")
            lines.append(f"        <ASCII \"{cpval}\">")
            lines.append("      >")
        lines.append("    >")
        lines.append("  >")
        lines.append(".")
        return "\n".join(lines)

    # ------------------ PHASE 4: RECIPE MANAGEMENT ------------------
    def generate_s7f19_pp_directory(self) -> str:
        return "// --- S7F19: Request Process Program Directory --- \nS7F19 W\n."


class SMLGenerationService:
    def __init__(self, storage: StorageService):
        self.storage = storage

    def generate_scripts(self, project_id: int) -> dict:
        batch_path = self.storage.spec_json_path(project_id, "project_batch")
        if not batch_path.exists():
            raise FileNotFoundError(f"Project batch specification not found for project {project_id}")

        spec_json = batch_path.read_text(encoding="utf-8")
        spec = EquipmentSpec.model_validate_json(spec_json)

        lines = [
            "// ========================================================================",
            f"// COMPREHENSIVE END-TO-END SML TEST SCRIPT FOR: {spec.ToolID}",
            f"// MODEL: {spec.Model}",
            f"// GENERATED ON: {datetime.datetime.now().isoformat()}",
            "// ========================================================================\n"
        ]

        generator = SMLGenerator(data_id=1)

        # === PHASE 1: ESTABLISH COMMUNICATIONS ===
        lines.append(generator.generate_s1f1_ping())
        lines.append("")
        lines.append(generator.generate_s1f13_establish_comm())
        lines.append("")
        
        # S1F11 Status Variables
        all_svids = []
        if spec.StatusVariables:
            all_svids = [sv.SVID for sv in spec.StatusVariables if isinstance(sv.SVID, int)]
        lines.append(generator.generate_s1f11_status_variables(all_svids[:20]))
        lines.append("")

        # S1F21 Data Variables
        all_dvids = []
        if spec.DataVariables:
            all_dvids = [dv.DvID for dv in spec.DataVariables if isinstance(dv.DvID, int)]
        lines.append(generator.generate_s1f11_status_variables(all_dvids[:20]).replace("S1F11", "S1F21").replace("Status", "Data"))
        lines.append("")

        # === PHASE 2: DATA COLLECTION SETUP ===
        reports_to_build = []
        if spec.Reports:
            for rpt in spec.Reports:
                try:
                    rptid = int(str(rpt.RPTID).replace("RPT_", ""))
                    svids = [int(v) for v in rpt.LinkedVIDs]
                    reports_to_build.append(ReportDefinition(report_id=rptid, svids=svids, name=rpt.Name))
                except (ValueError, TypeError):
                    continue

        if reports_to_build:
            lines.append(generator.generate_s2f33_define_report(reports_to_build))
            lines.append("")

        events_to_link = []
        ceids_to_enable = []
        if spec.Events:
            for evt in spec.Events:
                try:
                    ceid = int(evt.CEID)
                    ceids_to_enable.append(ceid)
                    if hasattr(evt, "LinkedReports") and evt.LinkedReports:
                        rpt_ids = []
                        for r in evt.LinkedReports:
                            r_str = str(r).replace("RPT_", "")
                            if r_str.isdigit():
                                rpt_ids.append(int(r_str))
                        if rpt_ids:
                            events_to_link.append(EventLink(ceid=ceid, report_ids=rpt_ids, name=getattr(evt, "EventName", "")))
                except Exception:
                    continue

        if events_to_link:
            lines.append(generator.generate_s2f35_link_event(events_to_link))
            lines.append("")
        if ceids_to_enable:
            lines.append(generator.generate_s2f37_enable_events(ceids_to_enable))
            lines.append("")

        if all_svids:
            lines.append(generator.generate_s2f23_trace_initialize(all_svids[:5]))
            lines.append("")

        # === PHASE 3: EQUIPMENT CONTROL ===
        lines.append(generator.generate_s2f41_host_command("START"))
        lines.append("")
        lines.append(generator.generate_s2f41_host_command("PP-SELECT", {"PPID": "TEST_RECIPE_01"}))
        lines.append("")
        
        # === PHASE 4: EVENT REPORTS (S6F11 & S6F1) ===
        lines.append("// === EXPECTED EVENT REPORTS (S6F11) ===")
        for ceid in ceids_to_enable[:5]: # Just do first 5 to show
            lines.append(f"// --- S6F11: Event Report for CEID {ceid} ---\n<S6F11 W\n  <L [3]\n    <U4 1>\n    <U4 {ceid}>\n    <L [0]>\n  >\n>\n.")
            lines.append("")

        lines.append("// === EXPECTED TRACE DATA (S6F1) ===")
        lines.append("// --- S6F1: Trace Data ---\n<S6F1 W\n  <L [4]\n    <U4 1>\n    <U4 100>\n    <ASCII \"2026061912000000\">\n    <L [0]>\n  >\n>\n.")
        lines.append("")

        lines.append(generator.generate_s2f41_host_command("STOP"))
        lines.append("")

        # === PHASE 5: RECIPES ===
        lines.append(generator.generate_s7f19_pp_directory())
        lines.append("")
        
        lines.append("// --- S7F1: Process Program Load Inquire ---")
        lines.append("<S7F1 W\n  <L [2]\n    <ASCII \"TEST_RECIPE_01\">\n    <U4 1000>\n  >\n>\n.")
        lines.append("")
        
        lines.append("// --- S7F3: Process Program Send ---")
        lines.append("<S7F3 W\n  <L [2]\n    <ASCII \"TEST_RECIPE_01\">\n    <ASCII \"PPBODY=FORMATTED\">\n  >\n>\n.")
        lines.append("")
        
        lines.append("// --- S7F5: Process Program Request ---")
        lines.append("<S7F5 W\n  <ASCII \"TEST_RECIPE_01\">\n>\n.")
        lines.append("")
        
        lines.append("// --- S7F17: Delete Process Program ---")
        lines.append("<S7F17 W\n  <L [1]\n    <ASCII \"TEST_RECIPE_01\">\n  >\n>\n.")
        lines.append("")

        script_content = "\n".join(lines)
        file_name = "ToolSpecificTest.txt"
        document_id = "ToolSpecificTest"

        metadata = self.storage.get_project(project_id)
        tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
        tool_char_dir.mkdir(parents=True, exist_ok=True)
        file_path = tool_char_dir / file_name
        file_path.write_text(script_content, encoding="utf-8")

        from source.services.test_script_service import TestScriptService
        test_script_service = TestScriptService()
        tests = test_script_service.parse_sml_to_tests(script_content)

        # Save the parsed tests as JSON
        json_path = tool_char_dir / "ToolSpecificTest.json"
        import json
        json_path.write_text(json.dumps(tests, indent=2), encoding="utf-8")

        # Create/Update document metadata
        doc_entry = next((d for d in metadata.Documents if d.DocumentID == document_id), None)
        if not doc_entry:
            doc_entry = DocumentMetadata(
                DocumentID=document_id,
                DocumentType=DocumentCategory.SML_SCRIPTS,
                FileName=file_name,
                FileSize=len(script_content.encode("utf-8")),
                Pages=1,
                Status="completed",
                UploadDate=datetime.datetime.now()
            )
            metadata.Documents.append(doc_entry)
        else:
            doc_entry.FileSize = len(script_content.encode("utf-8"))
            doc_entry.Status = "completed"

        self.storage._write_metadata(metadata)

        return tests
