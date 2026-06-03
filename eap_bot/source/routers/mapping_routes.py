import json
import logging
from pathlib import Path
from typing import List, Optional, Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from source.managers.service_container import container
from source.schemas.mapping import (
    MESMappingRequest,
    AutoMapRequest,
    MESTag,
    SaveMappingRequest
)
from source.schemas.secsgem import EquipmentSpec, StatusVariable, Event, Alarm
from source.services.storage_service import StorageService, StorageError, ProjectNotFoundError
from source.utils.template_parser import _extract_tags_from_template

logger = logging.getLogger(__name__)


def _safe_int(val: str) -> int:
    try:
        return int(val)
    except ValueError:
        return abs(hash(val)) % 10000000


class MappingAPI:
    def __init__(self):
        self.router = APIRouter(tags=["mapping"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.put("/UpdateMapping/{project_id}")(self.update_mapping)
        self.router.post("/AutoMap")(self.auto_map)

    def update_mapping(self, project_id: int, body: SaveMappingRequest):
        try:
            from source.managers.service_container import container
            # Use project_id from path if needed, override body
            body.project_id = project_id

            # Load raw template
            template_name = body.template if body.template.lower().endswith(".json") else f"{body.template}.json"
            template_path = Path("MESMapTemplates") / body.family / template_name
            
            if not template_path.exists():
                raise HTTPException(404, f"Raw template not found: {template_path}")
                
            with open(template_path, "r", encoding="utf-8") as f:
                raw_template = json.load(f)
                
            # Create lookup dictionaries for approved mappings
            # MESField/TagID is the key
            approved_vars = {m.MESField: m.EquipmentField for m in body.Mappings if m.EntityType == "variable"}
            approved_events = {m.MESField: m.EquipmentField for m in body.Mappings if m.EntityType == "event"}
            approved_alarms = {m.MESField: m.EquipmentField for m in body.Mappings if m.EntityType == "alarm"}
            
            # Populate EquipmentField in raw template
            if "Variables" in raw_template:
                for item in raw_template["Variables"]:
                    if item.get("MESField") in approved_vars:
                        item["EquipmentField"] = approved_vars[item["MESField"]]
                        
            if "Events" in raw_template:
                for item in raw_template["Events"]:
                    # Note: Events might not have 'MESField', they use 'EventName' in templates usually, 
                    # but our mapping engine maps to 'EventName' as TagID. Let's use EventName for lookup.
                    event_name = item.get("EventName")
                    if event_name in approved_events:
                        item["EquipmentField"] = approved_events[event_name]
                        
            if "Alarms" in raw_template:
                for item in raw_template["Alarms"]:
                    # Similarly for alarms, usually 'AlarmType'
                    alarm_type = item.get("AlarmType")
                    if alarm_type in approved_alarms:
                        item["EquipmentField"] = approved_alarms[alarm_type]
                        
            # Save the mapped template via storage service
            saved_path = self.storage.save_mes_mapping(body.project_id, body.family, body.template, raw_template)
            
            return {
                "ProjectID": body.project_id,
                "Status": "success",
                "Message": f"Mapping saved to {saved_path}"
            }
        except StorageError as exc:
            raise HTTPException(400, str(exc))
        except Exception as exc:
            logger.exception("Error saving mapping")
            raise HTTPException(500, str(exc))

    # async def upload_mes_tag_document(self, project_id: str, file: UploadFile = File(...)):
    #     if not file.filename or not file.filename.lower().endswith(".pdf"):
    #         raise HTTPException(400, "Only .pdf files are accepted for MES tags")
    #     try:
    #         document_id = self.storage.slugify(file.filename.replace(".pdf", ""))
    #         mes_path = self.storage.mes_tag_path(project_id, document_id)
    #         contents = await file.read()
    #         self.storage.save_pdf(mes_path, contents)
    #         extracted_tags = ["Tag1", "Tag2", "Tag3"]
    #         return {
    #             "ProjectID": project_id,
    #             "DocumentID": document_id,
    #             "Status": "success",
    #             "Message": "MES Tag document uploaded and tags extracted",
    #             "ExtractedTags": extracted_tags,
    #         }
    #     except StorageError as exc:
    #         raise HTTPException(500, str(exc))

    # def get_mes_mapping(self, project_id: int, body: MESMappingRequest):
    #     try:
    #         return container.project_service.get_mes_mapping(project_id, body)
    #     except ProjectNotFoundError as exc:
    #         raise HTTPException(404, str(exc)) from exc
    #     except FileNotFoundError as exc:
    #         raise HTTPException(404, str(exc)) from exc
    #     except Exception as exc:
    #         logger.error("MES mapping failed: %s", exc)
    #         raise HTTPException(500, f"Error generating mapping suggestions: {exc}") from exc

    def auto_map(self, body: AutoMapRequest):
        # 1. Resolve Equipment Spec
        try:
            metadata, aggregated = container.project_service.aggregate_project_data(body.project_id)
            spec = EquipmentSpec.model_validate(aggregated.model_dump())
        except Exception as exc:
            logger.error("Failed to load project extractions: %s", exc)
            raise HTTPException(404, f"Could not find extraction data for project {body.project_id}. {exc}")

        # 2. Resolve MES Tags
        template_filename = body.template
        if not template_filename.lower().endswith(".json"):
            template_filename = f"{template_filename}.json"

        template_path = (
            Path(__file__).resolve().parent.parent.parent
            / "MESMapTemplates"
            / body.family
            / template_filename
        )
        if not template_path.exists():
            raise HTTPException(404, f"MES template not found at {template_path}")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                raw_tags = json.load(f)
            target_tags = _extract_tags_from_template(raw_tags)
        except Exception as exc:
            logger.error("Failed to read/parse template %s: %s", template_path, exc)
            raise HTTPException(500, f"Error parsing template: {exc}")

        # 3. Filter by Entity if specified
        if body.entity:
            section_map = {
                "Variables": "Variables",
                "Events": "Events",
                "Alarms": "Alarms",
            }
            target_tags = [t for t in target_tags if t.tag_source == section_map[body.entity.value]]

        # 4. Get suggestions and save full template
        try:
            suggestions_response = container.mapping_service.suggest_mappings(spec, target_tags)
            
            full_template = raw_tags
            family = body.family
            template_filename = body.template
            if not template_filename.lower().endswith(".json"):
                template_filename = f"{template_filename}.json"
                    
            # Build the AutoMapping block with entity-specific ID key names
            raw_auto = suggestions_response.model_dump()
            for s in raw_auto.get("Suggestions", []):
                eid = s.pop("EquipmentID", "")
                etype = s.get("EntityType", "")
                if etype == "event":
                    s["EquipmentEventID"] = eid
                elif etype == "alarm":
                    s["EquipmentAlarmID"] = eid
                else:
                    s["EquipmentVariableID"] = eid
            for u in raw_auto.get("Unmapped", []):
                eid = u.pop("EquipmentID", "")
                etype = u.get("EntityType", "")
                if etype == "event":
                    u["EquipmentEventID"] = eid
                elif etype == "alarm":
                    u["EquipmentAlarmID"] = eid
                else:
                    u["EquipmentVariableID"] = eid
            full_template["AutoMapping"] = raw_auto
            
            # Auto-fill EquipmentField directly inside the template
            for sugg in suggestions_response.Suggestions:
                equipment_field = sugg.EquipmentField
                equipment_id = sugg.EquipmentID
                mes_field = sugg.MESField
                entity_type = sugg.EntityType
                
                for v in full_template.get("Variables", []):
                    if v.get("MESField") == mes_field:
                        v["EquipmentField"] = equipment_field
                        v["EquipmentVariableID"] = equipment_id
                        
                for e in full_template.get("Events", []):
                    if e.get("EventName") == mes_field:
                        e["EquipmentField"] = equipment_field
                        e["EquipmentEventID"] = equipment_id
                        
                for a in full_template.get("Alarms", []):
                    if a.get("AlarmType") == mes_field:
                        a["EquipmentField"] = equipment_field
                        a["EquipmentAlarmID"] = equipment_id
            
            if body.project_id is not None:
                self.storage.save_automap_result(body.project_id, family, template_filename, full_template)
                
            return full_template
            
        except Exception as exc:
            logger.error("Test mapping failed: %s", exc)
            raise HTTPException(500, f"Error generating mapping suggestions: {exc}") from exc