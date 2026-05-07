from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.managers.service_container import container
from app.schemas.project import ProjectCreate, ProjectDetail, ProjectOut
from app.schemas.secsgem import EquipmentSpec
from app.services.storage_service import (
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectExistsError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)
from app.utils.embedder import VectorStoreManager


class AskRequest(BaseModel):
    query: str = Field(min_length=1)


class ProjectAPI:
    def __init__(self):
        self.router = APIRouter(prefix="/projects", tags=["projects"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("", response_model=ProjectDetail, status_code=201)(self.create_project)
        self.router.get("", response_model=list[ProjectOut])(self.list_projects)
        self.router.get("/{project_id}", response_model=ProjectDetail)(self.get_project)
        self.router.delete("/{project_id}")(self.delete_project)
        self.router.post("/{project_id}/ask")(self.ask)

    def create_project(self, body: ProjectCreate):
        try:
            return self.storage.create_project(body.name)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectExistsError as exc:
            raise HTTPException(409, str(exc)) from exc

    def list_projects(self):
        try:
            return self.storage.list_projects()
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def get_project(self, project_id: str):
        try:
            return self.storage.get_project(project_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def delete_project(self, project_id: str):
        try:
            self.storage.delete_project(project_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {"status": "success", "message": f"Project '{project_id}' deleted"}

    def ask(self, project_id: str, body: AskRequest):
        try:
            self.storage.get_project(project_id)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            chunks = vector_store.search_with_filters(
                body.query, {"project_id": project_id}, k=1
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
            answer_text, source = qa_service.answer(body.query, spec)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "project_id": project_id,
            "document_id": document_id,
            "answer": answer_text,
            "source": source,
        }
