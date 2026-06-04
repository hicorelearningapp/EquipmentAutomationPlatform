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
            # Prefer the merged project_batch spec if it exists
            batch_path = self.storage.spec_json_path(project_id, "project_batch")
            if batch_path.exists():
                spec = EquipmentSpec.model_validate_json(batch_path.read_text(encoding="utf-8"))
            else:
                metadata = self.storage.get_project(project_id)
                spec = None
                for doc in metadata.Documents:
                    if doc.Status == "completed":
                        spec_json = self.storage.read_spec_json(project_id, doc.DocumentID)
                        spec = EquipmentSpec.model_validate_json(spec_json)
                        break
            
            if not spec:
                raise HTTPException(404, "No completed extracted equipment spec found for this project.")

            # Generate C# Constants using the new service
            # Default to HiCore.EAPIntegration.EquipmentConstants but can be customized
            code_content = container.smart_automation_service.generate_csharp_constants(spec)

            smart_code_dir = self.storage._project_dir(project_id) / self.storage.SMART_AUTO_CODE_DIR
            smart_code_dir.mkdir(parents=True, exist_ok=True)

            # Ensure the output filename is .cs since we are generating C#
            file_key = body.key
            if not file_key.endswith(".cs"):
                file_key = file_key.replace(".py", ".cs")
                if not file_key.endswith(".cs"):
                    file_key += ".cs"

            dst_path = smart_code_dir / file_key
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
