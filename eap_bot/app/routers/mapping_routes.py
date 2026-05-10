from fastapi import APIRouter, File, UploadFile, HTTPException
from app.schemas.mapping import MappingUpdateRequest
from app.services.storage_service import StorageService, StorageError


class MappingAPI:
    def __init__(self):
        self.router = APIRouter(tags=["mapping"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.put("/UpdateMapping/{project_id}")(self.update_mapping)
        self.router.post("/UploadMESTagDocument/{project_id}")(self.upload_mes_tag_document)

    def update_mapping(self, project_id: str, body: MappingUpdateRequest):
        return {
            "ProjectID": project_id,
            "Status": "success",
            "Message": f"Mappings updated for project {project_id}",
            "MESTags": body.MESTags
        }

    async def upload_mes_tag_document(self, project_id: str, file: UploadFile = File(...)):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only .pdf files are accepted for MES tags")

        try:
            # Use a slugified filename as document_id
            document_id = self.storage.slugify(file.filename.replace(".pdf", ""))
            mes_path = self.storage.mes_tag_path(project_id, document_id)
            
            contents = await file.read()
            self.storage.save_pdf(mes_path, contents)
            
            # [SKELETON] AI Extraction logic would go here
            extracted_tags = ["Tag1", "Tag2", "Tag3"] # Placeholder
            
            return {
                "ProjectID": project_id,
                "DocumentID": document_id,
                "Status": "success",
                "Message": "MES Tag document uploaded and tags extracted",
                "ExtractedTags": extracted_tags
            }
        except StorageError as exc:
            raise HTTPException(500, str(exc))
