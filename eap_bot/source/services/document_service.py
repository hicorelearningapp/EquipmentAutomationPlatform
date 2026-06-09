import io
import logging
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from source.config import settings
from source.schemas.project import DocumentCategory, VariableCategory
from source.schemas.secsgem import EquipmentSpec
from source.services.storage_service import (
    DocumentExistsError,
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)
from source.utils.embedder import VectorStoreManager

logger = logging.getLogger(__name__)


class DocumentService:
    """Handles document-level operations: upload, analysis, variable retrieval."""

    def __init__(self, storage: StorageService, container: Any) -> None:
        self.storage = storage
        self._container = container

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload_document(self, project_id: int, filename: str, contents: bytes) -> dict:
        ext = Path(filename).suffix.lower()
        if ext not in {".pdf", ".xlsx", ".txt"}:
            raise ValueError("Only .pdf, .xlsx, and .txt files are accepted")

        if len(contents) > settings.MAX_UPLOAD_SIZE:
            raise ValueError("File exceeds MAX_UPLOAD_SIZE")

        file_size = float(len(contents))

        if ext == ".pdf":
            pages = len(PdfReader(io.BytesIO(contents)).pages)
            doc_category = DocumentCategory.USER_MANUALS
        elif ext == ".xlsx":
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True)
            pages = len(wb.sheetnames)
            wb.close()
            doc_category = DocumentCategory.VARIABLE_FILES
        else:
            pages = 1
            doc_category = DocumentCategory.SML_SCRIPTS

        document_id, file_path, _ = self.storage.prepare_document_paths(
            project_id, filename, extension=ext
        )
        self.storage.save_pdf(file_path, contents)

        if ext == ".txt":
            tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
            tool_char_dir.mkdir(parents=True, exist_ok=True)
            dst_path = tool_char_dir / filename
            dst_path.write_bytes(contents)
            logger.info("Copied SML script %s to %s", filename, dst_path)

        document = self.storage.register_document(
            project_id=project_id,
            document_id=document_id,
            document_type=doc_category,
            filename=filename,
            file_size=file_size,
            pages=pages,
        )

        return {
            "Status": "uploaded",
            "DocumentID": document_id,
            "DocumentType": "Pending AI Classification",
            "FileName": document.FileName,
            "Pages": document.Pages,
            "FileSize": document.FileSize,
        }

    # ── Analysis ──────────────────────────────────────────────────────────────

    def analyze_document(self, project_id: int, document_id: str) -> dict:
        self.storage.increment_project_version(project_id)
        self.storage.write_sml_template(project_id)
        document = self.storage.get_document(project_id, document_id)

        if document.Status == "completed":
            spec_json = self.storage.read_spec_json(project_id, document_id)
            spec = EquipmentSpec.model_validate_json(spec_json)

            is_excel = document.FileName.lower().endswith(".xlsx")
            is_txt = document.FileName.lower().endswith(".txt")
            if not spec.Reports and not is_excel and not is_txt:
                logger.info("Reports missing in completed spec for %s/%s, generating now...", project_id, document_id)
                file_path = self._resolve_document_path(project_id, document)
                text = self._container.parser.extract_text(str(file_path))
                reports, links = self._container.report_service.generate(spec, text)
                if reports:
                    spec.Reports = reports
                    spec.EventReportLinks = links
                    json_path = self.storage.spec_json_path(project_id, document_id)
                    self.storage.save_spec_json(json_path, spec)

            return self._build_extraction_response(project_id, document_id, spec)

        is_excel = document.FileName.lower().endswith(".xlsx")
        is_txt = document.FileName.lower().endswith(".txt")

        try:
            file_path = self._resolve_document_path(project_id, document)
            doc_text: str = ""

            if is_excel:
                spec = self._container.extractor.extract_excel(file_path)
                if not spec.ToolID:
                    project_meta = self.storage.get_project(project_id)
                    spec.ToolID = project_meta.ProjectName
                    spec.ToolType = project_meta.Tool.value or "Semiconductor Processing Equipment"
                spec.Reports = []
                spec.EventReportLinks = []
            elif is_txt:
                project_meta = self.storage.get_project(project_id)
                spec = EquipmentSpec(
                    DocumentType=DocumentCategory.SML_SCRIPTS.value,
                    ToolID=project_meta.ProjectName,
                    ToolType=project_meta.Tool.value or "Semiconductor Processing Equipment",
                )
                spec.Reports = []
                spec.EventReportLinks = []
            else:
                doc_text = self._container.parser.extract_text(str(file_path))
                if not doc_text.strip():
                    raise ValueError("Could not extract any text from the PDF")

                tables_dir = self.storage.extracted_tables_path(project_id)
                spec = self._container.extractor.extract(doc_text, pdf_path=file_path, tables_dir=tables_dir)

                try:
                    reports, links = self._container.report_service.generate(spec, doc_text)
                    spec.Reports = reports
                    spec.EventReportLinks = links
                except Exception as exc:
                    logger.error("Report generation failed for %s/%s (non-fatal): %s", project_id, document_id, exc)
                    spec.Reports = []
                    spec.EventReportLinks = []

            json_path = self.storage.spec_json_path(project_id, document_id)
            self.storage.save_spec_json(json_path, spec)

            if doc_text:
                vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
                vector_store.add_document(
                    doc_text,
                    metadata={
                        "project_id": project_id,
                        "document_id": document_id,
                        "tool_id": spec.ToolID,
                    },
                )

            self.storage.complete_extraction(
                project_id=project_id,
                document_id=document_id,
                spec=spec,
            )
            self.storage.save_extracted_tables(project_id, spec)
        except Exception as e:
            logger.error("Analysis failed for %s/%s: %s", project_id, document_id, str(e))
            self.storage.mark_failed(project_id, document_id)
            return self._build_failed_response(project_id, document_id)

        return self._build_extraction_response(project_id, document_id, spec)

    # ── Variable Retrieval ────────────────────────────────────────────────────

    def get_variables(self, project_id: int, document_id: str, categories: str = None) -> dict:
        document = self.storage.get_document(project_id, document_id)
        if document.Status != "completed":
            raise ValueError("Document extraction is not completed yet.")

        spec_json = self.storage.read_spec_json(project_id, document_id)
        spec = EquipmentSpec.model_validate_json(spec_json)

        valid_values = {v.value for v in VariableCategory}

        if categories:
            tokens = [t.strip() for t in categories.split(",") if t.strip()]
            invalid = [t for t in tokens if t not in valid_values]
            if invalid:
                raise ValueError(
                    f"Invalid category value(s): {invalid}. Valid values are: {sorted(valid_values)}"
                )
            selected = [VariableCategory(t) for t in tokens]
        else:
            selected = list(VariableCategory)

        results_by_cat: dict[str, list[dict]] = {}
        total_count = 0

        for cat in selected:
            if cat == VariableCategory.STATUS_VARIABLE:
                items = [{"Category": "StatusVariable", "Data": sv.model_dump()} for sv in spec.StatusVariables]
            elif cat == VariableCategory.DATA_VARIABLE:
                items = [{"Category": "DataVariable", "Data": dv.model_dump()} for dv in spec.DataVariables]
            elif cat == VariableCategory.EVENT:
                items = [{"Category": "Event", "Data": ev.model_dump()} for ev in spec.Events]
            elif cat == VariableCategory.ALARM:
                items = [{"Category": "Alarm", "Data": al.model_dump()} for al in spec.Alarms]
            elif cat == VariableCategory.REMOTE_COMMAND:
                items = [{"Category": "RemoteCommand", "Data": rc.model_dump()} for rc in spec.RemoteCommands]
            elif cat == VariableCategory.STATE:
                items = [{"Category": "State", "Data": st.model_dump()} for st in spec.States]
            else:
                items = []

            if items:
                results_by_cat[cat.value] = items
                total_count += len(items)

        if not results_by_cat:
            raise DocumentNotFoundError(
                f"No data found for the requested categories in document '{document_id}'"
            )

        return {"Categories": list(results_by_cat.keys()), "TotalCount": total_count, "Results": results_by_cat}

    # ── Response Builders ─────────────────────────────────────────────────────

    def _build_failed_response(self, project_id: int, document_id: str) -> dict:
        from source.services.sml_template import SML_TEMPLATES
        return {
            "ProjectID": project_id,
            "ExtractionID": document_id,
            "ConfidenceScore": 0.0,
            "ExtractionStatus": "failed",
            "StatusVariables": [],
            "DataVariables": [],
            "Events": [],
            "Alarms": [],
            "RemoteCommands": [],
            "States": [],
            "StateTransitions": [],
            "Reports": [],
            "EventReportLinks": [],
            "SmlTemplate": SML_TEMPLATES,
        }

    def _build_extraction_response(self, project_id: int, document_id: str, spec: EquipmentSpec) -> dict:
        from source.services.sml_template import SML_TEMPLATES
        all_confidences = (
            [v.Confidence for v in spec.StatusVariables]
            + [e.Confidence for e in spec.Events]
            + [a.Confidence for a in spec.Alarms]
        )
        overall_confidence = (
            sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        )
        return {
            "ProjectID": project_id,
            "ExtractionID": document_id,
            "ConfidenceScore": round(overall_confidence, 3),
            "ExtractionStatus": "completed",
            "StatusVariables": [
                {"SVID": v.SVID, "Name": v.Name, "Description": v.Description or "", "DataType": v.DataType, "AccessType": v.AccessType}
                for v in spec.StatusVariables
            ],
            "DataVariables": [
                {"DvID": v.DvID, "Name": v.Name, "Unit": v.Unit or "", "ValueType": v.ValueType}
                for v in spec.DataVariables
            ],
            "Events": [
                # CHANGE e.Name to e.EventName
                {"CEID": e.CEID, "EventName": e.EventName, "Description": e.Description or ""}
                for e in spec.Events
            ],
            "Alarms": [
                {"AlarmID": a.AlarmID, "AlarmText": a.Name, "Severity": a.Severity}
                for a in spec.Alarms
            ],
            "RemoteCommands": [
                {"RCMD": rc.RCMD, "Description": rc.Description or "", "Parameters": [p.model_dump() for p in rc.Parameters]}
                for rc in spec.RemoteCommands
            ],
            "States": [
                {"StateID": st.StateID, "Name": st.Name, "Description": st.Description or ""}
                for st in spec.States
            ],
            "StateTransitions": [
                {"FromState": tr.FromState, "ToState": tr.ToState, "TriggerEvent": tr.TriggerEvent or "", "TriggerCommand": tr.TriggerCommand or "", "Manual": tr.Manual}
                for tr in spec.StateTransitions
            ],
            "Reports": [
                {"RPTID": r.RPTID, "Name": r.Name, "LinkedVIDs": r.LinkedVIDs, "Reasoning": r.Reasoning or ""}
                for r in spec.Reports
            ],
            "EventReportLinks": [
                {"CEID": lnk.CEID, "EventName": lnk.EventName, "RPTIDs": lnk.RPTIDs}
                for lnk in spec.EventReportLinks
            ],
            "SmlTemplate": SML_TEMPLATES,
        }

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _resolve_document_path(self, project_id: int, doc: Any) -> "Path":
        ext = Path(doc.FileName).suffix.lower()
        if ext == ".xlsx":
            return self.storage.document_excel_path(project_id, doc.DocumentID, ext=".xlsx")
        elif ext == ".txt":
            return self.storage.document_excel_path(project_id, doc.DocumentID, ext=".txt")
        return self.storage.document_pdf_path(project_id, doc.DocumentID)