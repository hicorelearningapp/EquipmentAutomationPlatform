import json
import logging
from pathlib import Path
from typing import List, Optional, Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from source.managers.service_container import container
from source.schemas.mapping import (
    MappingUpdateRequest,
    MESMappingRequest,
    TestEquipmentVariable,
    TestMESVariable,
    TestMappingRequest,
    MESTag
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
        # TODO: Mapping endpoints are temporarily disabled — uncomment when ready
        # self.router.put("/UpdateMapping/{project_id}")(self.update_mapping)
        # self.router.post("/UploadMESTagDocument/{project_id}")(self.upload_mes_tag_document)
        # self.router.post("/GetMESMapping/{project_id}")(self.get_mes_mapping)
        self.router.post("/TestMapping")(self.test_mapping)

    # def update_mapping(self, project_id: str, body: MappingUpdateRequest):
    #     return {
    #         "ProjectID": project_id,
    #         "Status": "success",
    #         "Message": f"Mappings updated for project {project_id}",
    #         "MESTags": body.MESTags,
    #     }

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

    def test_mapping(self, body: TestMappingRequest):
        # 1. Resolve Equipment Spec
        if body.equipment_variables is not None:
            status_vars = []
            events = []
            alarms = []
            for v in body.equipment_variables:
                eid = _safe_int(v.id)
                if v.entity_type == "variable":
                    status_vars.append(StatusVariable(
                        SVID=eid,
                        Name=v.name,
                        Description=v.description,
                        DataType=v.data_type,
                        AccessType="R"
                    ))
                elif v.entity_type == "event":
                    events.append(Event(
                        CEID=eid,
                        Name=v.name,
                        Description=v.description
                    ))
                elif v.entity_type == "alarm":
                    alarms.append(Alarm(
                        AlarmID=eid,
                        Name=v.name,
                        Severity="Warning",
                        Description=v.description
                    ))
            spec = EquipmentSpec(
                ToolID="TestTool",
                ToolType="TestType",
                StatusVariables=status_vars,
                Events=events,
                Alarms=alarms
            )
        elif body.project_id is not None:
            try:
                spec_path = self.storage.spec_json_path(body.project_id, "project_batch")
                if not spec_path.exists():
                    raise HTTPException(404, f"Could not find batch extraction for project {body.project_id}")
                spec_json = spec_path.read_text(encoding="utf-8")
                spec = EquipmentSpec.model_validate_json(spec_json)
            except ProjectNotFoundError as exc:
                raise HTTPException(404, str(exc)) from exc
        else:
            raise HTTPException(400, "Must provide either equipment_variables or project_id")

        # 2. Resolve MES Tags
        if body.mes_variables is not None:
            target_tags = []
            for v in body.mes_variables:
                target_tags.append(MESTag(
                    tag_id=v.tag_id,
                    name=v.name,
                    description=v.description,
                    expected_type=v.expected_type,
                ))
        elif body.family is not None and body.template is not None:
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
        else:
            raise HTTPException(400, "Must provide either mes_variables or family + template")

        # 3. Get suggestions
        try:
            return container.mapping_service.suggest_mappings(spec, target_tags)
        except Exception as exc:
            logger.error("Test mapping failed: %s", exc)
            raise HTTPException(500, f"Error generating mapping suggestions: {exc}") from exc