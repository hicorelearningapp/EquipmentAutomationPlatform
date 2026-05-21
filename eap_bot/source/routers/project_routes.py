import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from source.managers.service_container import container
from source.schemas.project import ProjectCreate, ProjectDetail, AskRequest, ProjectOut, DocumentCategory, ProjectUpdate, ProjectMetadata, AggregatedSpec
from source.schemas.secsgem import EquipmentSpec
from source.services.sml_template import SML_TEMPLATES
from source.services.storage_service import (
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectExistsError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)
from source.utils.embedder import VectorStoreManager

logger = logging.getLogger(__name__)


class ProjectAPI:
    def __init__(self):
        self.router = APIRouter(tags=["projects"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/AddProject", response_model=ProjectOut, status_code=201, response_model_by_alias=False)(self.create_project)
        self.router.get("/GetAllProjects", response_model=dict[str, list[ProjectOut]], response_model_by_alias=False)(self.list_projects)
        self.router.get("/LoadProject/{project_id}", response_model=ProjectDetail, response_model_by_alias=False)(self.load_project)
        self.router.put("/UpdateProject/{project_id}", response_model=ProjectOut, response_model_by_alias=False)(self.update_project)
        self.router.delete("/DeleteProject/{project_id}")(self.delete_project)
        self.router.get("/GetKnowledgeCategory/{project_id}")(self.get_knowledge_category)
        self.router.post("/Ask/{project_id}")(self.ask_project)

    def create_project(self, body: ProjectCreate):
        try:
            return self.storage.create_project(body)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectExistsError as exc:
            raise HTTPException(409, str(exc)) from exc

    def list_projects(self):
        try:
            projects = self.storage.list_projects()
            return {"ProjectInfo": projects}
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def load_project(self, project_id: int):
        try:
            metadata = self.storage.get_project(project_id)
            
            # 1. Batch Analysis for all documents
            for doc in metadata.Documents:
                if doc.Status != "completed":
                    logger.info(f"Auto-analyzing document {doc.DocumentID} for project {project_id}")
                    try:
                        is_excel = doc.FileName.lower().endswith(".xlsx")
                        is_txt = doc.FileName.lower().endswith(".txt")
                        text = ""

                        if is_excel:
                            file_path = self.storage.document_excel_path(project_id, doc.DocumentID, ext=".xlsx")
                            spec = container.extractor.extract_excel(file_path)
                            if not spec.ToolID:
                                spec.ToolID = metadata.ProjectName
                                spec.ToolType = metadata.Tool.value or "Semiconductor Processing Equipment"
                            spec.Reports = []
                            spec.EventReportLinks = []
                        elif is_txt:
                            file_path = self.storage.document_excel_path(project_id, doc.DocumentID, ext=".txt")
                            try:
                                tool_id = metadata.ProjectName
                                tool_type = metadata.Tool.value or "Semiconductor Processing Equipment"
                            except Exception:
                                tool_id = str(project_id)
                                tool_type = "Semiconductor Processing Equipment"
                            spec = EquipmentSpec(
                                DocumentType=DocumentCategory.SML_SCRIPTS.value,
                                ToolID=tool_id,
                                ToolType=tool_type,
                            )
                            spec.Reports = []
                            spec.EventReportLinks = []
                        else:
                            file_path = self.storage.document_pdf_path(project_id, doc.DocumentID)
                            text = container.parser.extract_text(str(file_path))
                            if not text.strip():
                                logger.warning(f"Empty text from {doc.DocumentID}")
                                continue

                            tables_dir = self.storage.extracted_tables_path(project_id)
                            spec = container.extractor.extract(text, pdf_path=file_path, tables_dir=tables_dir)

                            # Generate reports (non-fatal)
                            try:
                                reports, links = container.report_service.generate(spec, text)
                                spec.Reports = reports
                                spec.EventReportLinks = links
                            except Exception as exc:
                                logger.error(f"Report generation failed for {doc.DocumentID} (non-fatal): {exc}")
                                spec.Reports = []
                                spec.EventReportLinks = []

                        json_path = self.storage.spec_json_path(project_id, doc.DocumentID)
                        self.storage.save_spec_json(json_path, spec)
                        
                        if text:
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
                        logger.error(f"Failed to auto-analyze {doc.DocumentID}: {str(e)}")
                        self.storage.mark_failed(project_id, doc.DocumentID)

            # 2. Collect all extractions and merge them
            aggregated = AggregatedSpec()
            for doc in metadata.Documents:
                # Reload to get fresh status
                fresh_doc = self.storage.get_document(project_id, doc.DocumentID)
                if fresh_doc.Status == "completed":
                    try:
                        spec_json = self.storage.read_spec_json(project_id, doc.DocumentID)
                        spec = EquipmentSpec.model_validate_json(spec_json)
                        
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
                        logger.warning(f"Failed to read spec for {doc.DocumentID}: {e}")
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

            # Map aggregated arrays to omit Confidence/Value
            clean_aggregated = AggregatedSpec(
                StatusVariables=[
                    {
                        "SVID": v.SVID,
                        "Name": v.Name,
                        "Description": v.Description or "",
                        "DataType": v.DataType,
                        "AccessType": v.AccessType,
                    }
                    for v in aggregated.StatusVariables
                ],
                DataVariables=[
                    {
                        "DvID": v.DvID,
                        "Name": v.Name,
                        "Unit": v.Unit or "",
                        "ValueType": v.ValueType,
                    }
                    for v in aggregated.DataVariables
                ],
                Events=[
                    {
                        "CEID": e.CEID,
                        "EventName": e.Name,
                        "Description": e.Description or "",
                    }
                    for e in aggregated.Events
                ],
                Alarms=[
                    {
                        "AlarmID": a.AlarmID,
                        "AlarmText": a.Name,
                        "Severity": a.Severity,
                    }
                    for a in aggregated.Alarms
                ],
                RemoteCommands=[
                    {
                        "RCMD": rc.RCMD,
                        "Description": rc.Description or "",
                        "Parameters": [p.model_dump() for p in rc.Parameters],
                    }
                    for rc in aggregated.RemoteCommands
                ],
                States=[
                    {
                        "StateID": st.StateID,
                        "Name": st.Name,
                        "Description": st.Description or "",
                    }
                    for st in aggregated.States
                ],
                StateTransitions=[
                    {
                        "FromState": tr.FromState,
                        "ToState": tr.ToState,
                        "TriggerEvent": tr.TriggerEvent or "",
                        "TriggerCommand": tr.TriggerCommand or "",
                        "Manual": tr.Manual,
                    }
                    for tr in aggregated.StateTransitions
                ],
                Reports=[
                    {
                        "RPTID": r.RPTID,
                        "Name": r.Name,
                        "LinkedVIDs": r.LinkedVIDs,
                        "Reasoning": r.Reasoning or "",
                    }
                    for r in aggregated.Reports
                ],
                EventReportLinks=[
                    {
                        "CEID": lnk.CEID,
                        "EventName": lnk.EventName,
                        "RPTIDs": lnk.RPTIDs,
                    }
                    for lnk in aggregated.EventReportLinks
                ],
            )

            mapping = self.storage.get_mapping(project_id)
            self.storage.write_sml_template(project_id)

            # Reload metadata to get updated statuses and document list
            updated_metadata = self.storage.get_project(project_id)

            sml_data = SML_TEMPLATES

            return ProjectDetail(
                **updated_metadata.model_dump(),
                Extractions=clean_aggregated,
                Mappings=mapping,
                SmlTemplate=sml_data,
            )

        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def update_project(self, project_id: int, body: ProjectUpdate):
        try:
            return self.storage.update_project_metadata(project_id, body)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def delete_project(self, project_id: int):
        try:
            project = self.storage.get_project(project_id)
            self.storage.delete_project(project_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {"ProjectName": project.ProjectName, "ProjectID": project.ProjectID, "Status": "deleted"}

    def ask_project(self, project_id: int, request: AskRequest):
        try:
            self.storage.get_project(project_id)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            chunks = vector_store.search_with_filters(
                request.Question, {"project_id": project_id}, k=1
            )
            if not chunks:
                raise HTTPException(404, "No indexed content in this project yet")

            document_id = chunks[0].metadata.get("document_id")
            if not document_id:
                raise HTTPException(500, "Indexed chunk is missing document_id metadata")

            spec_json = self.storage.read_spec_json(project_id, document_id)
            spec = EquipmentSpec.model_validate_json(spec_json)
            qa_service = container.create_qa_service(
                vector_store,
                vector_filters={
                    "project_id": project_id,
                    "document_id": document_id,
                },
            )
            answer_text, source = qa_service.answer(request.Question, spec)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "ProjectID": project_id,
            "DocumentID": document_id,
            "Category": request.Category,
            "Answer": answer_text,
            "Source": source,
        }

    def get_knowledge_category(self, project_id: int):
        return {
            "ProjectID": project_id,
            "Categories": [t.value for t in DocumentCategory]
        }

    # ── Deduplication helpers ─────────────────────────────────────────────────

    @staticmethod
    def _dedup_by(items: list, key: str) -> list:
        """Keep first occurrence of each item by a primary-key attribute."""
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
        """Deduplicate state transitions by (FromState, ToState, TriggerEvent, TriggerCommand)."""
        seen = set()
        result = []
        for t in items:
            if hasattr(t, "FromState"):
                key = (t.FromState, t.ToState, t.TriggerEvent, t.TriggerCommand)
            else:
                key = (t.get("FromState"), t.get("ToState"), t.get("TriggerEvent"), t.get("TriggerCommand"))
            if key not in seen:
                seen.add(key)
                result.append(t)
        return result
