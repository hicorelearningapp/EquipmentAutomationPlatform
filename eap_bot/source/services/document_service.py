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

logger = logging.getLogger(__name__)


class DocumentService:
    """Handles document-level operations: upload, analysis, variable retrieval."""

    def __init__(self, storage: StorageService, container: Any) -> None:
        self.storage = storage
        self._container = container

    # ── Upload ────────────────────────────────────────────────────────────────

    def upload_document(self, project_id: int, filename: str, contents: bytes, doc_category: DocumentCategory) -> dict:
        if len(contents) > settings.MAX_UPLOAD_SIZE:
            raise ValueError("File exceeds MAX_UPLOAD_SIZE")

        file_size = float(len(contents))

        from source.services.document_strategies import DocumentProcessorFactory
        # The factory will raise a ValueError if the file extension is not supported
        strategy = DocumentProcessorFactory.get_strategy(filename, doc_category=doc_category)
        pages = strategy.get_pages(contents)

        ext = Path(filename).suffix.lower()

        document_id, file_path, _ = self.storage.prepare_document_paths(
            project_id, filename, extension=ext, doc_category=doc_category
        )
        self.storage.save_pdf(file_path, contents)

        document = self.storage.register_document(
            project_id=project_id,
            document_id=document_id,
            document_type=doc_category,
            filename=filename,
            file_size=file_size,
            pages=pages,
        )

        strategy.post_upload(
            project_id=project_id,
            document_id=document_id,
            document=document,
            file_path=file_path,
            storage=self.storage,
            container=self._container,
        )

        return {
            "Status": "uploaded",
            "DocumentID": document_id,
            "DocumentType": document.DocumentType.value if hasattr(document.DocumentType, "value") else document.DocumentType,
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

            from source.services.document_strategies import DocumentProcessorFactory, PdfProcessingStrategy
            strategy = DocumentProcessorFactory.get_strategy(document.FileName, doc_category=document.DocumentType)
            if not spec.Reports and isinstance(strategy, PdfProcessingStrategy):
                logger.info("Reports missing in completed spec for %s/%s, generating now...", project_id, document_id)
                file_path = self._resolve_document_path(project_id, document)
                text = self._container.parser.extract_text(str(file_path))
                reports = self._container.report_service.extract_builtin_reports(text)
                if reports:
                    spec.Reports = reports
                    json_path = self.storage.spec_json_path(project_id, document_id)
                    self.storage.save_spec_json(json_path, spec)

            return self._build_extraction_response(project_id, document_id, spec)

        try:
            file_path = self._resolve_document_path(project_id, document)
            from source.services.document_strategies import DocumentProcessorFactory
            strategy = DocumentProcessorFactory.get_strategy(document.FileName, doc_category=document.DocumentType)

            spec, pages = strategy.analyze(
                project_id=project_id,
                document_id=document_id,
                document=document,
                file_path=file_path,
                storage=self.storage,
                container=self._container,
            )

            json_path = self.storage.spec_json_path(project_id, document_id)
            self.storage.save_spec_json(json_path, spec)

            self.storage.complete_extraction(
                project_id=project_id,
                document_id=document_id,
                spec=spec,
            )
            self.storage.save_extracted_tables(project_id, spec)

            # ---------------------------------

            # Invalidate entity embeddings cache when spec changes
            cache_path = self.storage.spec_json_path(project_id, "project_batch").parent / "entity_embeddings.npz"
            if cache_path.exists():
                try:
                    cache_path.unlink()
                    logger.info("Invalidated entity embeddings cache at %s", cache_path)
                except Exception as e:
                    logger.warning("Failed to delete entity embeddings cache: %s", e)

        except Exception as e:
            logger.error("Analysis failed for %s/%s: %s", project_id, document_id, str(e))
            self.storage.mark_failed(project_id, document_id)
            return self._build_failed_response(project_id, document_id)

        return self._build_extraction_response(project_id, document_id, spec)

    def generate_predefined_questions(self, project_id: int, spec: EquipmentSpec) -> list[dict]:
        try:
            from source.services.equipment_extractor import PREDEFINED_QUESTIONS
            from source.utils.embedder import VectorStoreManager
            from concurrent.futures import ThreadPoolExecutor

            logger.info("Generating answers for predefined questions for project %s", project_id)
            
            # Use project-level vector store
            vector_store_path = self.storage.vectorstore_path(project_id)
            vstore = VectorStoreManager(vector_store_path)
            
            # QA Service without document_id filter (searches entire project vectorstore)
            qa_service = self._container.create_qa_service(
                vector_store=vstore,
                vector_filters=None
            )

            qa_results = []
            with ThreadPoolExecutor(max_workers=settings.EXTRACTOR_MAX_PARALLEL) as pool:
                # Pass None for document_id since it's project-wide
                futures = {
                    pool.submit(qa_service.answer, q, spec, project_id, None, self.storage): q
                    for q in PREDEFINED_QUESTIONS
                }
                future_map = {q: f for f, q in futures.items()}
                for q in PREDEFINED_QUESTIONS:
                    future = future_map[q]
                    try:
                        ans, source, _ = future.result()
                        qa_results.append({
                            "Question": q,
                            "Answer": ans,
                            "Source": source
                        })
                    except Exception as qa_exc:
                        logger.error("Failed to answer question '%s': %s", q, qa_exc)
                        qa_results.append({
                            "Question": q,
                            "Answer": "Error generating answer.",
                            "Source": "error"
                        })

            # Save as flat list
            self.storage.save_questions(project_id, qa_results)
            
            return qa_results

        except Exception as e:
            logger.error("Predefined Q&A generation failed for project %s: %s", project_id, e)
            return []

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
        from source.services.sml_template import build_sml_templates
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
            "SmlTemplate": build_sml_templates(project_id, self.storage),
            "Questions": self.storage.get_questions(project_id),
            "Mappings": self.storage.get_mapping(project_id).Mappings,
        }

    def _build_extraction_response(self, project_id: int, document_id: str, spec: EquipmentSpec) -> dict:
        from source.services.sml_template import build_sml_templates
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
                {
                    "CEID": e.CEID, 
                    "EventName": e.EventName, 
                    "Description": e.Description or "",
                    "LinkedVIDs": e.LinkedVIDs,
                    "LinkedReports": e.LinkedReports
                }
                for e in spec.Events
            ],
            "Alarms": [
                {"AlarmID": a.AlarmID, "AlarmName": a.AlarmName, "Severity": a.Severity}
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
                {
                    "RPTID": r.RPTID, 
                    "Name": r.Name, 
                    "Reasoning": r.Reasoning or "",
                    "LinkedVIDs": r.LinkedVIDs,
                    "Type": r.Type,
                    "Confidence": r.Confidence
                }
                for r in spec.Reports
            ],
            "SmlTemplate": build_sml_templates(project_id, self.storage),
            "Questions": self.storage.get_questions(project_id),
            "Mappings": self.storage.get_mapping(project_id).Mappings,
        }

    # ── Private Helpers ───────────────────────────────────────────────────────

    def _resolve_document_path(self, project_id: int, doc: Any) -> "Path":
        ext = Path(doc.FileName).suffix.lower()
        if ext == ".xlsx":
            return self.storage.document_excel_path(project_id, doc.DocumentID, ext=".xlsx")
        elif ext == ".txt":
            return self.storage.document_excel_path(project_id, doc.DocumentID, ext=".txt")
        return self.storage.document_pdf_path(project_id, doc.DocumentID)
