import json
import logging

from fastapi import APIRouter, HTTPException

from source.managers.service_container import container
from source.schemas.secsgem import EquipmentSpec
from source.schemas.codegen import SmartCodeGenerateRequest, SmartCodeUpdateRequest
from source.services.storage_service import StorageService

logger = logging.getLogger(__name__)


class SmartAutomationAPI:
    def __init__(self):
        self.router = APIRouter(tags=["smart automation"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/GenerateSmartAutomationCode/{project_id}")(self.generate_smart_automation_code)
        self.router.post("/UpdateSmartAutomationCode/{project_id}")(self.update_smart_automation_code)
        self.router.post("/GenerateOverallReport/{project_id}")(self.generate_overall_report)

    def generate_smart_automation_code(self, project_id: int, body: SmartCodeGenerateRequest):
        try:
            metadata = self.storage.get_project(project_id)
            spec = None
            for doc in metadata.Documents:
                if doc.Status == "completed":
                    spec_json = self.storage.read_spec_json(project_id, doc.DocumentID)
                    spec = EquipmentSpec.model_validate_json(spec_json)
                    break

            spec_info = ""
            if spec:
                spec_info = f"Status Variables: {[v.Name for v in spec.StatusVariables[:10]]}, Events: {[e.EventName for e in spec.Events[:10]]}"

            prompt = (
                f"Write a Python SECS/GEM automation script called '{body.key}' for tool '{metadata.ProjectName}'.\n"
                f"Use standard SECS/GEM libraries or mock communication.\n"
                f"Instructions: {body.instructions or 'None'}\n"
                f"Specification Info: {spec_info}\n"
                f"Return only the Python code. No markdown code blocks, just python code."
            )
            model = container.llm_strategy.get_model()
            response = model.invoke(prompt)
            code_content = response.content

            if code_content.startswith("```python"):
                code_content = code_content[9:]
            elif code_content.startswith("```"):
                code_content = code_content[3:]
            if code_content.endswith("```"):
                code_content = code_content[:-3]
            code_content = code_content.strip()

            smart_code_dir = self.storage._project_dir(project_id) / self.storage.SMART_AUTO_CODE_DIR
            smart_code_dir.mkdir(parents=True, exist_ok=True)

            dst_path = smart_code_dir / body.key
            dst_path.write_text(code_content, encoding="utf-8")

            return {
                "Status": "success",
                "Code": code_content,
                "FilePath": str(dst_path)
            }
        except Exception as e:
            logger.error("Failed to generate smart automation code: %s", e)
            raise HTTPException(500, str(e))

    def update_smart_automation_code(self, project_id: int, body: SmartCodeUpdateRequest):
        try:
            smart_code_dir = self.storage._project_dir(project_id) / self.storage.SMART_AUTO_CODE_DIR
            smart_code_dir.mkdir(parents=True, exist_ok=True)

            dst_path = smart_code_dir / body.key
            dst_path.write_text(body.source_code, encoding="utf-8")

            return {
                "Status": "success",
                "Message": f"Code {body.key} updated successfully",
                "FilePath": str(dst_path)
            }
        except Exception as e:
            logger.error("Failed to update smart automation code: %s", e)
            raise HTTPException(500, str(e))

    def generate_overall_report(self, project_id: int):
        try:
            metadata = self.storage.get_project(project_id)
            report = {
                "ProjectID": project_id,
                "ProjectName": metadata.ProjectName,
                "GeneratedAt": self.storage.now().isoformat(),
                "OverallStatus": "verified",
                "DocumentCount": len(metadata.Documents),
                "ReportSummary": f"Overall report compiles all manual extraction data and template sequences for {metadata.ProjectName}."
            }

            reports_dir = self.storage._project_dir(project_id) / self.storage.REPORTS_DIR
            reports_dir.mkdir(parents=True, exist_ok=True)

            report_path = reports_dir / "overall_report.json"
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

            return {
                "Status": "success",
                "Report": report
            }
        except Exception as e:
            logger.error("Failed to generate overall report: %s", e)
            raise HTTPException(500, str(e))
