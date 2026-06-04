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
            
            # Resolve Equipment Spec to get descriptions
            spec_vars_desc = {}
            spec_events_desc = {}
            spec_alarms_desc = {}
            try:
                _, aggregated = container.project_service.aggregate_project_data(body.project_id)
                spec = EquipmentSpec.model_validate(aggregated.model_dump())
                for v in spec.DataVariables + spec.StatusVariables:
                    vid = getattr(v, 'DvID', getattr(v, 'SVID', ''))
                    spec_vars_desc[str(vid)] = v.Description
                    spec_vars_desc[v.Name] = v.Description
                for e in spec.Events:
                    spec_events_desc[str(e.CEID)] = e.Description
                    spec_events_desc[e.EventName] = e.Description
                for a in spec.Alarms:
                    spec_alarms_desc[str(a.AlarmID)] = a.Description
                    spec_alarms_desc[a.Name] = a.Description
            except Exception:
                pass
            
            
            # Populate EquipmentField in raw template
            if "Variables" in raw_template:
                for item in raw_template["Variables"]:
                    if item.get("MESField") in approved_vars:
                        item["EquipmentField"] = approved_vars[item["MESField"]]
                        item["EquipmentDescription"] = spec_vars_desc.get(str(item["EquipmentField"]), "")
                        
            if "Events" in raw_template:
                for item in raw_template["Events"]:
                    # Note: Events might not have 'MESField', they use 'EventName' in templates usually, 
                    # but our mapping engine maps to 'EventName' as TagID. Let's use EventName for lookup.
                    event_name = item.get("EventName")
                    if event_name in approved_events:
                        item["EquipmentField"] = approved_events[event_name]
                        item["EquipmentDescription"] = spec_events_desc.get(str(item["EquipmentField"]), "")
                        
            if "Alarms" in raw_template:
                for item in raw_template["Alarms"]:
                    # Similarly for alarms, usually 'AlarmType'
                    alarm_type = item.get("AlarmType")
                    if alarm_type in approved_alarms:
                        item["EquipmentField"] = approved_alarms[alarm_type]
                        item["EquipmentDescription"] = spec_alarms_desc.get(str(item["EquipmentField"]), "")
                        
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
        spec_vars_desc = {}
        spec_events_desc = {}
        spec_alarms_desc = {}
        try:
            metadata, aggregated = container.project_service.aggregate_project_data(body.project_id)
            spec = EquipmentSpec.model_validate(aggregated.model_dump())
            for v in spec.DataVariables + spec.StatusVariables:
                vid = getattr(v, 'DvID', getattr(v, 'SVID', ''))
                spec_vars_desc[str(vid)] = v.Description
                spec_vars_desc[v.Name] = v.Description
            for e in spec.Events:
                spec_events_desc[str(e.CEID)] = e.Description
                spec_events_desc[e.EventName] = e.Description
            for a in spec.Alarms:
                spec_alarms_desc[str(a.AlarmID)] = a.Description
                spec_alarms_desc[a.Name] = a.Description
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
            
            # Use the new map_category parameter
            map_category_val = body.map_category.value if body.map_category else None
            target_tags = _extract_tags_from_template(raw_tags, map_category_val)
        except Exception as exc:
            logger.error("Failed to read/parse template %s: %s", template_path, exc)
            raise HTTPException(500, f"Error parsing template: {exc}")

        # 4. Get suggestions and save full template
        try:
            suggestions_response = container.mapping_service.suggest_mappings(spec, target_tags)
            
            family = body.family
            template_filename = body.template
            if not template_filename.lower().endswith(".json"):
                template_filename = f"{template_filename}.json"

            existing = self.storage.load_automap_result(body.project_id, family, template_filename)

            if existing is not None and body.map_category is not None:
                full_template = existing
                cat_val = body.map_category.value
                
                # Reset only this section from raw template
                full_template[cat_val] = raw_tags.get(cat_val, [])
                
                # Keep old suggestions not in this category
                cat_type_map = {"Variables": "variable", "Events": "event", "Alarms": "alarm"}
                old_suggestions = full_template.get("AutoMapping", {}).get("Suggestions", [])
                old_unmapped = full_template.get("AutoMapping", {}).get("Unmapped", [])
                
                kept_suggestions = [s for s in old_suggestions if s.get("EntityType") != cat_type_map[cat_val]]
                kept_unmapped = [u for u in old_unmapped if u.get("EntityType") != cat_type_map[cat_val]]
            else:
                full_template = raw_tags
                kept_suggestions = []
                kept_unmapped = []
                    
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
            
            raw_auto["Suggestions"] = kept_suggestions + raw_auto.get("Suggestions", [])
            raw_auto["Unmapped"] = kept_unmapped + raw_auto.get("Unmapped", [])
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
                        v["EquipmentDescription"] = spec_vars_desc.get(str(equipment_field), "")
                        
                for e in full_template.get("Events", []):
                    if e.get("EventName") == mes_field:
                        e["EquipmentField"] = equipment_field
                        e["EquipmentEventID"] = equipment_id
                        e["EquipmentDescription"] = spec_events_desc.get(str(equipment_field), "")
                        
                for a in full_template.get("Alarms", []):
                    if a.get("AlarmType") == mes_field:
                        a["EquipmentField"] = equipment_field
                        a["EquipmentAlarmID"] = equipment_id
                        a["EquipmentDescription"] = spec_alarms_desc.get(str(equipment_field), "")
            
            if body.project_id is not None:
                self.storage.save_automap_result(body.project_id, family, template_filename, full_template)
                
            return full_template
            
        except Exception as exc:
            logger.error("Test mapping failed: %s", exc)
            raise HTTPException(500, f"Error generating mapping suggestions: {exc}") from exc