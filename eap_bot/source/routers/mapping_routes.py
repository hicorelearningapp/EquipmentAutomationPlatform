import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from source.managers.service_container import container
from source.schemas.mapping import MappingUpdateRequest, MESMappingRequest
from source.services.storage_service import StorageService, StorageError, ProjectNotFoundError

logger = logging.getLogger(__name__)


class MappingAPI:
    def __init__(self):
        self.router = APIRouter(tags=["mapping"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.put("/UpdateMapping/{project_id}")(self.update_mapping)
        self.router.post("/UploadMESTagDocument/{project_id}")(self.upload_mes_tag_document)
        self.router.post("/GetMESMapping/{project_id}")(self.get_mes_mapping)

    def update_mapping(self, project_id: str, body: MappingUpdateRequest):
        return {
            "ProjectID": project_id,
            "Status": "success",
            "Message": f"Mappings updated for project {project_id}",
            "MESTags": body.MESTags,
        }

    async def upload_mes_tag_document(self, project_id: str, file: UploadFile = File(...)):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only .pdf files are accepted for MES tags")
        try:
            document_id = self.storage.slugify(file.filename.replace(".pdf", ""))
            mes_path = self.storage.mes_tag_path(project_id, document_id)
            contents = await file.read()
            self.storage.save_pdf(mes_path, contents)
            extracted_tags = ["Tag1", "Tag2", "Tag3"]
            return {
                "ProjectID": project_id,
                "DocumentID": document_id,
                "Status": "success",
                "Message": "MES Tag document uploaded and tags extracted",
                "ExtractedTags": extracted_tags,
            }
        except StorageError as exc:
            raise HTTPException(500, str(exc))

    def get_mes_mapping(self, project_id: int, body: MESMappingRequest):
        try:
            return container.project_service.get_mes_mapping(project_id, body)
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except Exception as exc:
            logger.error("MES mapping failed: %s", exc)
            raise HTTPException(500, f"Error generating mapping suggestions: {exc}") from exc