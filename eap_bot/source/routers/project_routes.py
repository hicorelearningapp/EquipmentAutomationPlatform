import logging

from fastapi import APIRouter, HTTPException

from source.managers.service_container import container
from source.schemas.project import (
    AggregatedSpec,
    AskRequest,
    DocumentCategory,
    ProjectCreate,
    ProjectDetail,
    ProjectMetadata,
    ProjectOut,
    ProjectUpdate,
)
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
            metadata, aggregated = container.project_service.aggregate_project_data(project_id)

            clean_aggregated = self._build_clean_aggregated(aggregated)
            mapping = self.storage.get_mapping(project_id)
            self.storage.write_sml_template(project_id)
            updated_metadata = self.storage.get_project(project_id)

            return ProjectDetail(
                **updated_metadata.model_dump(),
                Extractions=clean_aggregated,
                Mappings=mapping,
                SmlTemplate=SML_TEMPLATES,
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
                vector_filters={"project_id": project_id, "document_id": document_id},
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
            "Categories": [t.value for t in DocumentCategory],
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_clean_aggregated(self, aggregated: EquipmentSpec) -> AggregatedSpec:
        return AggregatedSpec(
            StatusVariables=[
                {"SVID": v.SVID, "Name": v.Name, "Description": v.Description or "", "DataType": v.DataType, "AccessType": v.AccessType}
                for v in aggregated.StatusVariables
            ],
            DataVariables=[
                {"DvID": v.DvID, "Name": v.Name, "Unit": v.Unit or "", "ValueType": v.ValueType}
                for v in aggregated.DataVariables
            ],
            Events=[
                {"CEID": e.CEID, "EventName": e.Name, "Description": e.Description or ""}
                for e in aggregated.Events
            ],
            Alarms=[
                {"AlarmID": a.AlarmID, "AlarmText": a.Name, "Severity": a.Severity}
                for a in aggregated.Alarms
            ],
            RemoteCommands=[
                {"RCMD": rc.RCMD, "Description": rc.Description or "", "Parameters": [p.model_dump() for p in rc.Parameters]}
                for rc in aggregated.RemoteCommands
            ],
            States=[
                {"StateID": st.StateID, "Name": st.Name, "Description": st.Description or ""}
                for st in aggregated.States
            ],
            StateTransitions=[
                {"FromState": tr.FromState, "ToState": tr.ToState, "TriggerEvent": tr.TriggerEvent or "", "TriggerCommand": tr.TriggerCommand or "", "Manual": tr.Manual}
                for tr in aggregated.StateTransitions
            ],
            Reports=[
                {"RPTID": r.RPTID, "Name": r.Name, "LinkedVIDs": r.LinkedVIDs, "Reasoning": r.Reasoning or ""}
                for r in aggregated.Reports
            ],
            EventReportLinks=[
                {"CEID": lnk.CEID, "EventName": lnk.EventName, "RPTIDs": lnk.RPTIDs}
                for lnk in aggregated.EventReportLinks
            ],
        )