from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import logging

from app.managers.service_container import container
from app.schemas.project import ProjectCreate, ProjectDetail, AskRequest, ProjectOut, ProjectMetadata
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

logger = logging.getLogger(__name__)


class ProjectAPI:
    def __init__(self):
        self.router = APIRouter(tags=["projects"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/AddProject", response_model=ProjectDetail, status_code=201)(self.create_project)
        self.router.get("/GetAllProjects", response_model=dict[str, list[ProjectOut]])(self.list_projects)
        self.router.get("/LoadProject/{project_id}", response_model=ProjectDetail)(self.load_project)
        self.router.delete("/DeleteProject/{project_id}")(self.delete_project)
        self.router.get("/GetKnowledgeCategory/{project_id}")(self.get_knowledge_category)
        self.router.post("/Ask/{project_id}")(self.ask)

    def create_project(self, body: ProjectCreate):
        try:
            return self.storage.create_project(
                project_name=body.ProjectName,
                vendor_name=body.VendorName,
                tool=body.Tool,
            )
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

    def load_project(self, project_id: str):
        try:
            metadata = self.storage.get_project(project_id)
            
            # 1. Batch Analysis for all documents
            for doc in metadata.Documents:
                if doc.Status != "completed":
                    logger.info(f"Auto-analyzing document {doc.DocumentId} for project {project_id}")
                    try:
                        pdf_path = self.storage.document_pdf_path(project_id, doc.DocumentId)
                        text = container.parser.extract_text(str(pdf_path))
                        if not text.strip():
                            logger.warning(f"Empty text from {doc.DocumentId}")
                            continue

                        spec = container.extractor.extract(text)
                        json_path = self.storage.spec_json_path(project_id, doc.DocumentId)
                        self.storage.save_spec_json(json_path, spec)
                        
                        vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
                        vector_indexed = vector_store.add_document(
                            text,
                            metadata={
                                "project_id": project_id,
                                "document_id": doc.DocumentId,
                                "tool_id": spec.tool_id,
                            },
                        )
                        self.storage.complete_extraction(
                            project_id=project_id,
                            document_id=doc.DocumentId,
                            spec=spec,
                            vector_indexed=vector_indexed,
                        )
                    except Exception as e:
                        logger.error(f"Failed to auto-analyze {doc.DocumentId}: {str(e)}")
                        self.storage.mark_failed(project_id, doc.DocumentId)

            # 2. Collect all extractions and mappings
            extractions = []
            for doc in metadata.Documents:
                if doc.Status == "completed":
                    try:
                        spec_json = self.storage.read_spec_json(project_id, doc.DocumentId)
                        extractions.append(EquipmentSpec.model_validate_json(spec_json))
                    except Exception:
                        continue

            mapping = self.storage.get_mapping(project_id)
            
            # Reload metadata to get updated statuses
            updated_metadata = self.storage.get_project(project_id)
            
            return ProjectDetail(
                **updated_metadata.model_dump(),
                Extractions=extractions,
                Mappings=mapping
            )

        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def delete_project(self, project_id: str):
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

    def ask(self, project_id: str, body: AskRequest):
        try:
            self.storage.get_project(project_id)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            chunks = vector_store.search_with_filters(
                body.Question, {"project_id": project_id}, k=1
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
            answer_text, source = qa_service.answer(body.Question, spec)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "ProjectID": project_id,
            "DocumentID": document_id,
            "Category": body.Category,
            "Answer": answer_text,
            "Source": source,
        }

    def get_knowledge_category(self, project_id: str):
        from app.schemas.project import DocumentType
        return {
            "ProjectID": project_id,
            "Categories": [t.value for t in DocumentType]
        }
