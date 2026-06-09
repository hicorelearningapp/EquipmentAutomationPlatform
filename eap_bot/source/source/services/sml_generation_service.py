import datetime
from source.schemas.secsgem import EquipmentSpec
from source.schemas.project import DocumentCategory, DocumentMetadata
from source.services.storage_service import StorageService

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
            f"// Tool Setup Script generated for Tool ID: {spec.ToolID}",
            f"// Generation Time: {datetime.datetime.now().isoformat()}",
            ""
        ]

        # S2F33: Define Reports
        if spec.Reports:
            lines.append("// --- Define Reports (S2F33) ---")
            for rpt in spec.Reports:
                lines.append(f"S2F33 W")
                lines.append(f"  <L [2]")
                lines.append(f"    <U4 {rpt.RPTID}>  // {rpt.Name}")
                lines.append(f"    <L [{len(rpt.LinkedVIDs)}]")
                for vid in rpt.LinkedVIDs:
                    lines.append(f"      <U4 {vid}>")
                lines.append(f"    >")
                lines.append(f"  >")
            lines.append("")

        # S2F35: Link Reports to Events
        if spec.Events:
            events_with_reports = [e for e in spec.Events if hasattr(e, "LinkedReports") and e.LinkedReports]
            if events_with_reports:
                lines.append("// --- Link Reports (S2F35) ---")
                for evt in events_with_reports:
                    lines.append(f"S2F35 W")
                    lines.append(f"  <L [2]")
                    lines.append(f"    <U4 {evt.CEID}>  // {evt.EventName}")
                    lines.append(f"    <L [{len(evt.LinkedReports)}]")
                    for rpt_id in evt.LinkedReports:
                        # try to parse rpt_id to int, otherwise assume it's a string identifier mapped to integer, wait SECS GEM RPTID can be a string? 
                        # In standard GEM, RPTID is usually numeric U4/U2. If it's something like 'RPT_001', it might not compile as U4.
                        # For generated SML, we'll write whatever it is, typically the user handles it.
                        rpt_val = str(rpt_id).replace("RPT_", "")
                        lines.append(f"      <U4 {rpt_val}>")
                    lines.append(f"    >")
                    lines.append(f"  >")
                lines.append("")

        # S2F37: Enable Events
        if spec.Events:
            lines.append("// --- Enable Events (S2F37) ---")
            lines.append(f"S2F37 W")
            lines.append(f"  <Boolean True>")
            lines.append(f"  <L [{len(spec.Events)}]")
            for evt in spec.Events:
                lines.append(f"    <U4 {evt.CEID}>  // {evt.EventName}")
            lines.append(f"  >")
            lines.append("")

        script_content = "\n".join(lines)
        file_name = f"sml_setup_{project_id}.txt"
        document_id = f"sml_setup_{project_id}"

        metadata = self.storage.get_project(project_id)
        
        tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
        tool_char_dir.mkdir(parents=True, exist_ok=True)
        file_path = tool_char_dir / file_name
        file_path.write_text(script_content, encoding="utf-8")

        doc_entry = None
        for d in metadata.Documents:
            if d.DocumentID == document_id:
                doc_entry = d
                break
        
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
        
        spec_doc = EquipmentSpec(
            DocumentType=DocumentCategory.SML_SCRIPTS.value,
            ToolID=spec.ToolID,
            ToolType=spec.ToolType,
            Reports=[]
        )
        json_path = self.storage.spec_json_path(project_id, document_id)
        self.storage.save_spec_json(json_path, spec_doc)
        self.storage.complete_extraction(project_id, document_id, spec_doc)

        return {
            "Status": "success",
            "Message": "SML script generated and registered successfully",
            "FileName": file_name,
            "DocumentID": document_id,
            "ScriptContent": script_content
        }
