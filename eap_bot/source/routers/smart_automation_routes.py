import json
import logging

from fastapi import APIRouter, HTTPException

from source.managers.service_container import container
from source.schemas.secsgem import EquipmentSpec
from source.schemas.codegen import SmartCodeGenerateRequest, SmartCodeUpdateRequest


logger = logging.getLogger(__name__)


class SmartAutomationAPI:
    def __init__(self):
        self.router = APIRouter(tags=["smart automation"])
        self.storage = container.storage
        self.register_routes()

    def register_routes(self):
        self.router.post("/GenerateSmartAutomationCode/{project_id}")(self.generate_smart_automation_code)
        self.router.post("/UpdateSmartAutomationCode/{project_id}")(self.update_smart_automation_code)
        self.router.post("/GenerateOverallReport/{project_id}")(self.generate_overall_report)

    def generate_smart_automation_code(self, project_id: int, body: SmartCodeGenerateRequest):
        try:
            return container.smart_automation_service.generate_smart_automation_code_workflow(project_id, body.key)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to generate smart automation code: %s", e)
            raise HTTPException(500, str(e))

    def update_smart_automation_code(self, project_id: int, body: SmartCodeUpdateRequest):
        try:
            return container.smart_automation_service.update_smart_automation_code_workflow(project_id, body.key, body.source_code)
        except Exception as e:
            logger.error("Failed to update smart automation code: %s", e)
            raise HTTPException(500, str(e))

    def generate_overall_report(self, project_id: int):
        try:
            return container.smart_automation_service.generate_overall_report_workflow(project_id)
        except Exception as e:
            logger.error("Failed to generate overall report: %s", e)
            raise HTTPException(500, str(e))
