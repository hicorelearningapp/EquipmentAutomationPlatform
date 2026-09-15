import logging

from fastapi import APIRouter, HTTPException

from source.managers.service_container import container
from source.schemas.project import (
    AggregatedSpec,
    AskRequest,
    ProjectCreate,
    ProjectDetail,
    ProjectMetadata,
    ProjectOut,
    ProjectUpdate,
    ProjectDetailsResponse,
    SystemSummaryResponse,
)
from source.schemas.secsgem import EquipmentSpec
from source.services.sml_template import build_sml_templates
from source.services.storage_service import (
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectExistsError,
    ProjectNotFoundError,
    StorageError,
)
from source.utils.embedder import VectorStoreManager

logger = logging.getLogger(__name__)


class ProjectAPI:
    def __init__(self):
        self.router = APIRouter(tags=["projects"])
        self.storage = container.storage
        self.register_routes()

    def register_routes(self):
        self.router.post("/CreateProject", response_model=ProjectOut, status_code=201, response_model_by_alias=False)(self.create_project)
        self.router.get("/GetAllProjects", response_model=dict[str, list[ProjectOut]], response_model_by_alias=False)(self.list_projects)
        self.router.get("/LoadProject/{project_id}", response_model=ProjectDetail, response_model_by_alias=False)(self.load_project)
        self.router.put("/UpdateProject/{project_id}", response_model=ProjectOut, response_model_by_alias=False)(self.update_project)
        self.router.delete("/DeleteProject/{project_id}")(self.delete_project)
        self.router.post("/ReAnalyzeProject/{project_id}", response_model=ProjectDetail, response_model_by_alias=False)(self.reanalyze_project)
        self.router.get("/GetKnowledgeCategory/{project_id}", response_model=list[str])(self.get_knowledge_category)
        self.router.post("/Ask/{project_id}", responses={500: {"description": "Internal Server Error"}})(self.ask_project)
        self.router.get("/GetProjectDetails/{project_id}", response_model=ProjectDetailsResponse, response_model_by_alias=False)(self.get_project_details)
        self.router.get("/GetSystemSummary", response_model=SystemSummaryResponse, response_model_by_alias=False)(self.get_system_summary)

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
            return container.project_service.load_project_workflow(project_id)
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
        except ProjectExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
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

    def reanalyze_project(self, project_id: int):
        try:
            return container.project_service.reanalyze_project_workflow(project_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def get_project_details(self, project_id: int):
        try:
            return container.project_service.get_project_details(project_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def get_system_summary(self):
        try:
            return container.project_service.get_system_summary()
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def ask_project(self, project_id: int, request: AskRequest):
        try:
            return container.project_service.ask_project_workflow(project_id, request.Question, request.DocumentCategory)
        except HTTPException:
            raise
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        except Exception as exc:
            import traceback
            traceback.print_exc()
            raise HTTPException(500, f"Internal Server Error: {str(exc)}") from exc

    def get_knowledge_category(self, project_id: int) -> list[str]:
        try:
            return container.project_service.get_knowledge_category_workflow(project_id)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

