import io
import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pypdf import PdfReader

from source.config import settings
from source.managers.service_container import container
from source.schemas.project import DocumentCategory
from source.schemas.secsgem import EquipmentSpec
from source.schemas.codegen import ScriptUpdateRequest, SmartCodeGenerateRequest, SmartCodeUpdateRequest
from source.services.sml_template import SML_TEMPLATES
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


def updatetestcode(content: str) -> str:
    # Placeholder for test code modification/updates
    # For now, returns content as-is without modifications
    return content


class EquipmentAPI:
    def __init__(self):
        self.router = APIRouter()
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/UploadDocument/{project_id}", tags=["documents"])(self.upload_document)
        self.router.get("/Analyze/{project_id}/{document_id}", response_model_by_alias=False, tags=["documents"])(self.analyze)
        self.router.get("/AnalyzeProject/{project_id}", response_model_by_alias=False, tags=["documents"])(self.analyze_project)
        self.router.get("/Analyze/{project_id}/{document_id}/report", tags=["documents"])(self.download_report)
        self.router.delete("/DeleteDocument/{project_id}/{document_id}", tags=["documents"])(self.delete_document)
        self.router.post("/UpdateExtraction/{project_id}", tags=["documents"])(self.update_extraction)

    async def upload_document(
        self,
        project_id: int,
        file: UploadFile = File(...),
    ):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only .pdf files are accepted")

        contents = await file.read()
        if len(contents) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(400, "File exceeds MAX_UPLOAD_SIZE")

        file_size = float(len(contents))
        pages = len(PdfReader(io.BytesIO(contents)).pages)

        try:
            document_id, pdf_path, _ = self.storage.prepare_document_paths(
                project_id, file.filename
            )
            self.storage.save_pdf(pdf_path, contents)
            document = self.storage.register_document(
                project_id=project_id,
                document_id=document_id,
                document_type=DocumentCategory.USER_MANUALS,
                filename=file.filename,
                file_size=file_size,
                pages=pages,
            )
        except DocumentExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "Status": "uploaded",
            "DocumentID": document_id,
            "DocumentType": "Pending AI Classification",
            "FileName": document.FileName,
            "Pages": document.Pages,
            "FileSize": document.FileSize,
        }

    def analyze(self, project_id: int, document_id: str):
        try:
            self.storage.increment_project_version(project_id)
            self.storage.write_sml_template(project_id)
            document = self.storage.get_document(project_id, document_id)
        except (InvalidSlugError, ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        if document.Status == "completed":
            try:
                spec_json = self.storage.read_spec_json(project_id, document_id)
                spec = EquipmentSpec.model_validate_json(spec_json)

                if not spec.Reports:
                    logger.info("Reports missing in completed spec for %s/%s, generating now...", project_id, document_id)
                    pdf_path = self.storage.document_pdf_path(project_id, document_id)
                    text = container.parser.extract_text(str(pdf_path))
                    reports, links = container.report_service.generate(spec, text)
                    if reports:
                        spec.Reports = reports
                        spec.EventReportLinks = links
                        json_path = self.storage.spec_json_path(project_id, document_id)
                        self.storage.save_spec_json(json_path, spec)
            except StorageError as exc:
                raise HTTPException(500, str(exc)) from exc
            except Exception as exc:
                logger.error("Self-healing report generation failed (non-fatal): %s", exc)

            return self._build_extraction_response(project_id, document_id, spec)

        try:
            pdf_path = self.storage.document_pdf_path(project_id, document_id)
            text = container.parser.extract_text(str(pdf_path))
            if not text.strip():
                raise ValueError("Could not extract any text from the PDF")

            tables_dir = self.storage.extracted_tables_path(project_id)
            spec = container.extractor.extract(text, pdf_path=pdf_path, tables_dir=tables_dir)

            try:
                reports, links = container.report_service.generate(spec, text)
                spec.Reports = reports
                spec.EventReportLinks = links
            except Exception as exc:
                logger.error(
                    "Report generation failed for %s/%s (non-fatal): %s",
                    project_id, document_id, exc,
                )
                spec.Reports = []
                spec.EventReportLinks = []

            json_path = self.storage.spec_json_path(project_id, document_id)
            self.storage.save_spec_json(json_path, spec)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            vector_store.add_document(
                text,
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
            logger.error(f"Analysis failed for {project_id}/{document_id}: {str(e)}")
            self.storage.mark_failed(project_id, document_id)
            return self._build_failed_response(project_id, document_id)

        return self._build_extraction_response(project_id, document_id, spec)

    def _build_failed_response(self, project_id: int, document_id: str) -> dict:
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

    def _build_extraction_response(
        self, project_id: int, document_id: str, spec: EquipmentSpec
    ) -> dict:
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
                {
                    "SVID": v.SVID,
                    "Name": v.Name,
                    "Description": v.Description or "",
                    "DataType": v.DataType,
                    "AccessType": v.AccessType,
                }
                for v in spec.StatusVariables
            ],
            "DataVariables": [
                {
                    "DvID": v.DvID,
                    "Name": v.Name,
                    "Unit": v.Unit or "",
                    "ValueType": v.ValueType,
                }
                for v in spec.DataVariables
            ],
            "Events": [
                {
                    "CEID": e.CEID,
                    "EventName": e.Name,
                    "Description": e.Description or "",
                }
                for e in spec.Events
            ],
            "Alarms": [
                {
                    "AlarmID": a.AlarmID,
                    "AlarmText": a.Name,
                    "Severity": a.Severity,
                }
                for a in spec.Alarms
            ],
            "RemoteCommands": [
                {
                    "RCMD": rc.RCMD,
                    "Description": rc.Description or "",
                    "Parameters": [p.model_dump() for p in rc.Parameters],
                }
                for rc in spec.RemoteCommands
            ],
            "States": [
                {
                    "StateID": st.StateID,
                    "Name": st.Name,
                    "Description": st.Description or "",
                }
                for st in spec.States
            ],
            "StateTransitions": [
                {
                    "FromState": tr.FromState,
                    "ToState": tr.ToState,
                    "TriggerEvent": tr.TriggerEvent or "",
                    "TriggerCommand": tr.TriggerCommand or "",
                    "Manual": tr.Manual,
                }
                for tr in spec.StateTransitions
            ],
            "Reports": [
                {
                    "RPTID": r.RPTID,
                    "Name": r.Name,
                    "LinkedVIDs": r.LinkedVIDs,
                    "Reasoning": r.Reasoning or "",
                }
                for r in spec.Reports
            ],
            "EventReportLinks": [
                {
                    "CEID": lnk.CEID,
                    "EventName": lnk.EventName,
                    "RPTIDs": lnk.RPTIDs,
                }
                for lnk in spec.EventReportLinks
            ],
            "SmlTemplate": SML_TEMPLATES,
        }

    def download_report(self, project_id: int, document_id: str):
        try:
            document = self.storage.get_document(project_id, document_id)
            content = self.storage.read_spec_json(project_id, document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        headers = {
            "Content-Disposition": f'attachment; filename="{document_id}_{document.ToolID}.json"'
        }
        return Response(content=content, media_type="application/json", headers=headers)

    def delete_document(self, project_id: int, document_id: str):
        try:
            self.storage.delete_document(project_id, document_id)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            vector_store.remove_document(document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {
            "Status": "success",
            "Message": f"Document {document_id} deleted",
        }

    def update_extraction(self, project_id: int, spec: EquipmentSpec):
        try:
            self.storage.increment_project_version(project_id)
            json_path = self.storage.spec_json_path(project_id, "project_batch")
            self.storage.save_spec_json(json_path, spec)
            return {"Status": "success", "Message": "Extraction updated successfully"}
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def analyze_project(self, project_id: int):
        try:
            self.storage.increment_project_version(project_id)
            self.storage.write_sml_template(project_id)

            # Copy script templates to project directory after running through updatetestcode
            try:
                from source.services.sml_template import SCRIPTS_DIR
                tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
                tool_char_dir.mkdir(parents=True, exist_ok=True)

                for script_name in ["general_gem_testing.txt", "tool_characterisation_testing.txt"]:
                    src_path = SCRIPTS_DIR / script_name
                    if src_path.exists():
                        original_content = src_path.read_text(encoding="utf-8")
                        processed_content = updatetestcode(original_content)
                        dst_path = tool_char_dir / script_name
                        dst_path.write_text(processed_content, encoding="utf-8")
                        logger.info("Saved processed script %s to %s", script_name, dst_path)
            except Exception as e:
                logger.error("Failed to copy/process script templates for project %s: %s", project_id, e)

            metadata = self.storage.get_project(project_id)
        except (InvalidSlugError, ProjectNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        # 1. Batch Analysis for all pending documents
        for doc in metadata.Documents:
            if doc.Status != "completed":
                logger.info("Auto-analyzing document %s for project %s", doc.DocumentID, project_id)
                try:
                    pdf_path = self.storage.document_pdf_path(project_id, doc.DocumentID)
                    text = container.parser.extract_text(str(pdf_path))
                    if not text.strip():
                        logger.warning("Empty text from %s", doc.DocumentID)
                        continue

                    tables_dir = self.storage.extracted_tables_path(project_id)
                    spec = container.extractor.extract(text, pdf_path=pdf_path, tables_dir=tables_dir)

                    # Generate reports (non-fatal)
                    try:
                        reports, links = container.report_service.generate(spec, text)
                        spec.Reports = reports
                        spec.EventReportLinks = links
                    except Exception as exc:
                        logger.error("Report generation failed for %s (non-fatal): %s", doc.DocumentID, exc)
                        spec.Reports = []
                        spec.EventReportLinks = []

                    json_path = self.storage.spec_json_path(project_id, doc.DocumentID)
                    self.storage.save_spec_json(json_path, spec)

                    vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
                    vector_store.add_document(
                        text,
                        metadata={
                            "project_id": project_id,
                            "document_id": doc.DocumentID,
                            "tool_id": spec.ToolID,
                        },
                    )
                    self.storage.complete_extraction(
                        project_id=project_id,
                        document_id=doc.DocumentID,
                        spec=spec,
                    )
                    self.storage.save_extracted_tables(project_id, spec)
                except Exception as e:
                    logger.error("Failed to auto-analyze %s: %s", doc.DocumentID, e)
                    self.storage.mark_failed(project_id, doc.DocumentID)

        # 2. Collect all extractions and merge them
        aggregated = EquipmentSpec(
            DocumentType=metadata.Documents[0].DocumentType if metadata.Documents else "GEM Manual",
            ToolID=metadata.ProjectName,
            ToolType=metadata.Tool.value if hasattr(metadata, "Tool") and metadata.Tool else "Semiconductor Processing Equipment",
        )

        # Reload metadata to get fresh statuses
        metadata = self.storage.get_project(project_id)
        for doc in metadata.Documents:
            if doc.Status == "completed":
                try:
                    spec_json = self.storage.read_spec_json(project_id, doc.DocumentID)
                    spec = EquipmentSpec.model_validate_json(spec_json)

                    if not spec.Reports:
                        logger.info("Reports missing in completed spec for %s/%s, generating now...", project_id, doc.DocumentID)
                        pdf_path = self.storage.document_pdf_path(project_id, doc.DocumentID)
                        text = container.parser.extract_text(str(pdf_path))
                        reports, links = container.report_service.generate(spec, text)
                        if reports:
                            spec.Reports = reports
                            spec.EventReportLinks = links
                            json_path = self.storage.spec_json_path(project_id, doc.DocumentID)
                            self.storage.save_spec_json(json_path, spec)

                    aggregated.StatusVariables.extend(spec.StatusVariables)
                    aggregated.DataVariables.extend(spec.DataVariables)
                    aggregated.Events.extend(spec.Events)
                    aggregated.Alarms.extend(spec.Alarms)
                    aggregated.RemoteCommands.extend(spec.RemoteCommands)
                    aggregated.States.extend(spec.States)
                    aggregated.StateTransitions.extend(spec.StateTransitions)
                    aggregated.Reports.extend(spec.Reports)
                    aggregated.EventReportLinks.extend(spec.EventReportLinks)
                except Exception as e:
                    logger.warning("Failed to read/merge spec for %s: %s", doc.DocumentID, e)
                    continue

        # 3. Deduplicate aggregated arrays by primary ID
        aggregated.StatusVariables = self._dedup_by(aggregated.StatusVariables, "SVID")
        aggregated.DataVariables = self._dedup_by(aggregated.DataVariables, "DvID")
        aggregated.Events = self._dedup_by(aggregated.Events, "CEID")
        aggregated.Alarms = self._dedup_by(aggregated.Alarms, "AlarmID")
        aggregated.RemoteCommands = self._dedup_by(aggregated.RemoteCommands, "RCMD")
        aggregated.States = self._dedup_by(aggregated.States, "StateID")
        aggregated.StateTransitions = self._dedup_transitions(aggregated.StateTransitions)
        aggregated.Reports = self._dedup_by(aggregated.Reports, "RPTID")
        aggregated.EventReportLinks = self._dedup_by(aggregated.EventReportLinks, "CEID")

        return self._build_extraction_response(project_id, "project_batch", aggregated)

    @staticmethod
    def _dedup_by(items: list, key: str) -> list:
        seen = set()
        result = []
        for item in items:
            val = getattr(item, key, None) if hasattr(item, key) else item.get(key)
            if val not in seen:
                seen.add(val)
                result.append(item)
        return result

    @staticmethod
    def _dedup_transitions(items: list) -> list:
        seen = set()
        result = []
        for t in items:
            key = (
                getattr(t, "FromState", None),
                getattr(t, "ToState", None),
                getattr(t, "TriggerEvent", None),
                getattr(t, "TriggerCommand", None),
            )
            if key not in seen:
                seen.add(key)
                result.append(t)
        return result

