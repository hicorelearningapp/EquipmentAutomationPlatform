import json
import logging

from typing import Optional, List
from fastapi import APIRouter, HTTPException, File, UploadFile, Form

from pathlib import Path

from source.managers.service_container import container
from source.schemas.secsgem import EquipmentSpec
from source.schemas.codegen import ScriptUpdateRequest
from source.schemas.test_script import GenerateTestScriptsRequest
from source.schemas.project import DocumentCategory
from source.services.document_service import DocumentService
from source.services.storage_service import StorageService, ProjectNotFoundError
from source.services.test_script_service import TestScriptService

logger = logging.getLogger(__name__)


class ToolCharacterizationAPI:
    def __init__(self):
        self.router = APIRouter(tags=["tool characterizations"])
        self.storage = StorageService()
        self.test_script_service = TestScriptService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/GenerateTestScripts/{project_id}")(self.generate_test_scripts)
        self.router.post("/UpdateToolCharacterizationScript/{project_id}")(self.update_tool_char_script)
        # self.router.post("/GenerateToolCharacterisationReportSummary/{project_id}")(self.generate_tool_char_report_summary)
        self.router.post("/GenerateTestSummary/{project_id}")(self.generate_test_summary)
        self.router.get("/GetTestSummary/{project_id}")(self.get_test_summary)

    def generate_test_scripts(self, project_id: int, body: GenerateTestScriptsRequest):
        try:
            filename = body.filename

            # Normalise filename for check
            sml_filename = filename
            if not sml_filename.endswith(".txt"):
                if sml_filename == "ToolCharacterisationTesting":
                    sml_filename = "tool_characterisation_testing.txt"
                elif sml_filename == "GeneralGEMTesting":
                    sml_filename = "general_gem_testing.txt"
                else:
                    sml_filename = f"{sml_filename}.txt"

            # Check project-specific directory first
            project_file_path = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR / sml_filename
            if project_file_path.exists():
                file_path = project_file_path
            else:
                # Fallback to the respective JSON in GEMTestScriptTemplates
                if sml_filename == "tool_characterisation_testing.txt":
                    fallback_filename = "ToolCharacterizationTestScriptjson (1).txt"
                elif sml_filename == "general_gem_testing.txt":
                    fallback_filename = "GeneraltestScriptjson (1).txt"
                else:
                    fallback_filename = sml_filename

                file_path = Path(__file__).resolve().parent.parent.parent / "GEMTestScriptTemplates" / fallback_filename

            if not file_path.exists():
                raise HTTPException(404, f"Test script file '{filename}' not found.")

            content = file_path.read_text(encoding="utf-8")
            try:
                tests = json.loads(content)
            except Exception as json_err:
                logger.info("Content is not valid JSON, trying SML parser fallback: %s", json_err)
                try:
                    tests = self.test_script_service.parse_sml_to_tests(content)
                except Exception as parse_err:
                    raise HTTPException(400, f"Failed to parse content as either JSON or SML: {parse_err}")

            tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
            tool_char_dir.mkdir(parents=True, exist_ok=True)

            json_filename = Path(filename).stem + ".json"
            dst_path = tool_char_dir / json_filename
            dst_path.write_text(json.dumps(tests, indent=2), encoding="utf-8")

            return tests
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Failed to generate and parse test scripts: %s", e)
            raise HTTPException(500, str(e))

    def update_tool_char_script(self, project_id: int, body: ScriptUpdateRequest):
        try:
            filename = body.key
            if not filename.endswith(".txt"):
                if filename == "ToolCharacterisationTesting":
                    filename = "tool_characterisation_testing.txt"
                elif filename == "GeneralGEMTesting":
                    filename = "general_gem_testing.txt"
                else:
                    filename = f"{filename}.txt"

            tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
            tool_char_dir.mkdir(parents=True, exist_ok=True)

            dst_path = tool_char_dir / filename
            dst_path.write_text(body.script, encoding="utf-8")

            return {
                "Status": "success",
                "Message": f"Script {body.key} updated successfully",
                "FilePath": str(dst_path)
            }
        except Exception as e:
            logger.error("Failed to update tool characterization script: %s", e)
            raise HTTPException(500, str(e))

    # def generate_tool_char_report_summary(self, project_id: int):
    #     try:
    #         metadata = self.storage.get_project(project_id)
    #         test_summary = {
    #             "ProjectID": project_id,
    #             "ProjectName": metadata.ProjectName,
    #             "Timestamp": self.storage.now().isoformat(),
    #             "Status": "completed",
    #             "TotalTests": 15,
    #             "PassedTests": 15,
    #             "FailedTests": 0,
    #             "SummaryReport": "All SECS/GEM message structures characterized successfully."
    #         }
    # 
    #         test_summary_dir = self.storage._project_dir(project_id) / self.storage.TEST_SUMMARY_DIR
    #         test_summary_dir.mkdir(parents=True, exist_ok=True)
    # 
    #         summary_path = test_summary_dir / "test_summary.json"
    #         summary_path.write_text(json.dumps(test_summary, indent=2), encoding="utf-8")
    # 
    #         return {
    #             "Status": "success",
    #             "Summary": test_summary
    #         }
    #     except Exception as e:
    #         logger.error("Failed to generate report summary: %s", e)
    #         raise HTTPException(500, str(e))

    async def generate_test_summary(
        self,
        project_id: int,
        summary_json: UploadFile = File(...),
        secs_log: Optional[List[UploadFile]] = File(default=None)
    ):
        try:
            try:
                summary_json_bytes = await summary_json.read()
                summary_json_data = json.loads(summary_json_bytes.decode("utf-8"))
            except Exception as e:
                raise HTTPException(400, f"summary_json is not a valid JSON file: {e}")

            try:
                first_item = summary_json_data[0] if isinstance(summary_json_data, list) else summary_json_data
                conn = first_item.get("Connection", {})
                tool_id = str(conn.get("DeviceId", ""))
                ip_address = str(conn.get("IpAddress", ""))

                if not tool_id:
                    raise ValueError("DeviceId not found in summary_json Connection block")
            except Exception as e:
                raise HTTPException(400, f"Failed to extract DeviceId/IpAddress from summary_json: {e}")

            secs_log_data = None
            if secs_log is not None:
                secs_log_data_list = []
                doc_service = None
                for file in secs_log:
                    if not file.filename:
                        continue
                    
                    filename = file.filename.lower()
                    file_bytes = await file.read()
                    
                    if filename.endswith(".txt"):
                        if doc_service is None:
                            doc_service = DocumentService(self.storage, container)
                        doc_service.upload_document(
                            project_id=project_id,
                            filename=file.filename,
                            contents=file_bytes,
                            doc_category=DocumentCategory.SML_SCRIPTS
                        )
                    elif filename.endswith(".json"):
                        try:
                            json_data = json.loads(file_bytes.decode("utf-8"))
                            secs_log_data_list.append(json_data)
                        except Exception as e:
                            raise HTTPException(400, f"file {file.filename} is not a valid JSON file: {e}")
                
                if secs_log_data_list:
                    secs_log_data = secs_log_data_list[0] if len(secs_log_data_list) == 1 else secs_log_data_list

            saved_path = self.storage.save_test_summary(
                project_id=project_id,
                tool_id=tool_id,
                ip_address=ip_address,
                secs_log=secs_log_data,
                summary_json=summary_json_data
            )
            return {
                "Status": "success",
                "Message": "Test summary saved successfully",
                "Path": saved_path
            }
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to save test summary: %s", exc)
            raise HTTPException(500, str(exc)) from exc

    async def get_test_summary(self, project_id: int, tool_id: Optional[str] = None):
        try:
            summary = self.storage.get_latest_test_summary(project_id, tool_id)
            if summary is None:
                raise HTTPException(404, "Test summary not found.")
            return summary
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("Failed to retrieve test summary: %s", exc)
            raise HTTPException(500, str(exc)) from exc
