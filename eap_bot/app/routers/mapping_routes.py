from fastapi import APIRouter, File, UploadFile, HTTPException
from app.schemas.mapping import MappingUpdateRequest, ProjectMapping
from app.schemas.secsgem import EquipmentSpec
from app.services.storage_service import StorageService, StorageError
from app.managers.service_container import container
import json


class MappingAPI:
    def __init__(self):
        self.router = APIRouter(tags=["mapping"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.put("/UpdateMapping/{project_id}")(self.update_mapping)
        self.router.post("/UploadMESTagDocument/{project_id}")(self.upload_mes_tag_document)

    def update_mapping(self, project_id: str):
        try:
            # 1. Get MES Tags from storage (previously extracted from PDF)
            mes_tags = self.storage.get_mes_tags(project_id)
            
            if not mes_tags:
                raise HTTPException(400, "No MES tags provided or found for this project.")

            # 2. Get all successful extractions
            metadata = self.storage.get_project(project_id)
            extractions = []
            for doc in metadata.Documents:
                if doc.Status == "completed":
                    try:
                        spec_json = self.storage.read_spec_json(project_id, doc.DocumentId)
                        extractions.append(EquipmentSpec.model_validate_json(spec_json))
                    except Exception:
                        continue
            
            if not extractions:
                raise HTTPException(400, "No equipment specifications found. Please upload manuals first.")

            # 3. Perform AI Mapping
            mapping = container.mapping_service.generate_mapping(project_id, mes_tags, extractions)
            
            # 4. Save and return
            self.storage.save_mapping(project_id, mapping)
            return mapping

        except StorageError as exc:
            raise HTTPException(500, str(exc))

    async def upload_mes_tag_document(self, project_id: str, file: UploadFile = File(...)):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only .pdf files are accepted for MES tags")

        try:
            document_id = self.storage.slugify(file.filename.replace(".pdf", ""))
            mes_path = self.storage.mes_tag_path(project_id, document_id)
            
            contents = await file.read()
            self.storage.save_pdf(mes_path, contents)
            
            # AI Extraction of tags from PDF
            text = container.parser.extract_text(str(mes_path))
            
            prompt = f"""Extract a list of MES (Manufacturing Execution System) tags from this document.
For each tag, provide its 'Name' and a brief 'Description'.
Return as a JSON object with a 'Tags' key containing a list of objects.

TEXT:
{text}
"""
            model = container.llm_strategy.get_model(temperature=0, require_json=True)
            raw = model.invoke(prompt).content
            tags_data = json.loads(raw).get("Tags", [])
            
            self.storage.save_mes_tags(project_id, tags_data)
            
            return {
                "ProjectID": project_id,
                "DocumentID": document_id,
                "Status": "success",
                "Message": "MES Tag document uploaded and tags extracted",
                "ExtractedTags": [t["Name"] for t in tags_data]
            }
        except Exception as exc:
            raise HTTPException(500, str(exc))
