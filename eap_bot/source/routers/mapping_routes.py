import json
import logging
from pathlib import Path
from typing import List, Optional, Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from source.managers.service_container import container
from source.schemas.mapping import (
    MESMappingRequest,
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
            approved_vars = {m.MESField: m.EquipmentFieldName for m in body.Mappings if m.EntityType == "variable"}
            approved_events = {m.MESField: m.EquipmentFieldName for m in body.Mappings if m.EntityType == "event"}
            approved_alarms = {m.MESField: m.EquipmentFieldName for m in body.Mappings if m.EntityType == "alarm"}
            
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
            
            
            # Populate EquipmentFieldName in raw template
            if "Variables" in raw_template:
                for item in raw_template["Variables"]:
                    if item.get("MESVariableName") in approved_vars:
                        item["EquipmentVariableName"] = approved_vars[item["MESVariableName"]]
                        item["EquipmentDescription"] = spec_vars_desc.get(str(item["EquipmentVariableName"]), "")
                        
            if "Events" in raw_template:
                for item in raw_template["Events"]:
                    event_name = item.get("MESEventName")
                    if event_name in approved_events:
                        item["EquipmentEventName"] = approved_events[event_name]
                        item["EquipmentDescription"] = spec_events_desc.get(str(item["EquipmentEventName"]), "")
                        
            if "Alarms" in raw_template:
                for item in raw_template["Alarms"]:
                    alarm_name = item.get("MESAlarmName")
                    if alarm_name in approved_alarms:
                        item["EquipmentAlarmName"] = approved_alarms[alarm_name]
                        item["EquipmentDescription"] = spec_alarms_desc.get(str(item["EquipmentAlarmName"]), "")
                        
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

    def auto_map(self, project_id: int, body: dict) -> dict:
        # We accept raw dict so extra sections pass through untouched
        from source.schemas.mapping import AutoMapSectionRequest
        from source.utils.template_parser import _extract_tags_from_template

        # Validate just the sections we care about
        try:
            req = AutoMapSectionRequest.model_validate(body)
        except Exception as exc:
            raise HTTPException(422, f"Invalid request body format: {exc}")

        # 1. Resolve Equipment Spec
        spec_vars_desc = {}
        spec_events_desc = {}
        spec_alarms_desc = {}
        try:
            try:
                spec_json = container.project_service.storage.read_spec_json(project_id, "project_batch")
                spec = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                metadata, aggregated = container.project_service.aggregate_project_data(project_id)
                spec = EquipmentSpec.model_validate(aggregated.model_dump())
                
            for v in spec.DataVariables + spec.StatusVariables:
                vid = getattr(v, 'DvID', getattr(v, 'SVID', ''))
                desc = getattr(v, 'Description', '-')
                spec_vars_desc[str(vid)] = desc
                spec_vars_desc[v.Name] = desc
            for e in spec.Events:
                spec_events_desc[str(e.CEID)] = e.Description
                spec_events_desc[e.EventName] = e.Description
            for a in spec.Alarms:
                spec_alarms_desc[str(a.AlarmID)] = a.Description
                spec_alarms_desc[a.AlarmName] = a.Description
        except Exception as exc:
            logger.error("Failed to load project extractions: %s", exc)
            raise HTTPException(404, f"Could not find extraction data for project {project_id}. {exc}")

        # 2. Resolve MES Tags
        try:
            target_tags = _extract_tags_from_template(body)
        except Exception as exc:
            logger.error("Failed to parse sections: %s", exc)
            raise HTTPException(400, f"Error parsing sections: {exc}")

        if not target_tags:
            return body  # Nothing to map

        # 4. Get suggestions
        try:
            suggestions_response = container.mapping_service.suggest_mappings(spec, target_tags)
            
            # Map of MESField -> Suggestion for easy lookup
            sugg_map = {}
            for sugg in suggestions_response.Suggestions:
                # the tag is the mes_field
                sugg_map[sugg.MESField] = sugg
                
            # 5. Fill out the response sections
            result = dict(body)
            
            # Helper to update lists in place
            def update_list(section_key, match_key, eq_key, id_key, desc_dict):
                items = result.get(section_key, [])
                for item in items:
                    val = item.get(match_key)
                    # If this item has already been mapped, skip LLM suggestion but still populate description
                    existing_eq = item.get(eq_key)
                    if existing_eq:
                        item["EquipmentDescription"] = desc_dict.get(str(existing_eq), "")
                        continue
                        
                    if val in sugg_map:
                        sugg = sugg_map[val]
                        item[eq_key] = sugg.EquipmentFieldName
                        item["EquipmentDescription"] = desc_dict.get(str(sugg.EquipmentFieldName), "")
                        item[id_key] = sugg.EquipmentID
            
            update_list("Variables", "MESVariableName", "EquipmentVariableName", "VID", spec_vars_desc)
            update_list("Events", "MESEventName", "EquipmentEventName", "CEID", spec_events_desc)
            update_list("Alarms", "MESAlarmName", "EquipmentAlarmName", "ALID", spec_alarms_desc)
            
            return result
            
        except Exception as exc:
            logger.error("AutoMap Section failed: %s", exc)
            raise HTTPException(500, f"Error generating section mappings: {exc}") from exc
