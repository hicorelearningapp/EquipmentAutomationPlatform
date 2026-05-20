import json
import logging
from pathlib import Path
from fastapi import APIRouter, File, UploadFile, HTTPException
from source.schemas.mapping import MappingUpdateRequest, MESMappingRequest, MESTag
from source.schemas.secsgem import EquipmentSpec
from source.services.storage_service import StorageService, StorageError

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

    def get_mes_mapping(self, project_id: int, body: MESMappingRequest):
        try:
            # 1. Read spec
            spec_path = self.storage.spec_json_path(project_id, "project_batch")
            if not spec_path.exists():
                raise HTTPException(404, f"Could not find batch extraction for project {project_id}")
            spec_json = spec_path.read_text(encoding="utf-8")
            spec = EquipmentSpec.model_validate_json(spec_json)
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to read project batch spec: %s", exc)
            raise HTTPException(404, f"Could not find batch extraction for project {project_id}")

        # 2. Locate and load the requested MES template JSON file
        template_filename = body.template
        if not template_filename.lower().endswith(".json"):
            template_filename = f"{template_filename}.json"

        template_path = Path(__file__).resolve().parent.parent.parent / "MESMapTemplates" / body.family / template_filename
        if not template_path.exists():
            raise HTTPException(404, f"MES template not found at {template_path}")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                raw_tags = json.load(f)
            target_tags = [MESTag.model_validate(t) for t in raw_tags]
        except Exception as exc:
            logger.error("Failed to parse MES template JSON: %s", exc)
            raise HTTPException(400, f"Invalid JSON format in template: {exc}")

        # 3. Call suggest_mappings
        try:
            from source.managers.service_container import container
            mapping_response = container.mapping_service.suggest_mappings(spec, target_tags)
            return mapping_response
        except Exception as exc:
            logger.error("LLM mapping suggestion failed: %s", exc)
            raise HTTPException(500, f"Error generating mapping suggestions: {exc}")

