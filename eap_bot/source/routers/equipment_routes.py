import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Body
from fastapi.responses import Response

from source.managers.service_container import container
from source.schemas.project import DocumentCategory
from source.services.storage_service import (
    DocumentExistsError,
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)

logger = logging.getLogger(__name__)


class EquipmentAPI:
    def __init__(self):
        self.router = APIRouter()
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/UploadDocument/{project_id}", tags=["documents"])(self.upload_document)
        self.router.get("/Analyze/{project_id}/{document_id}", response_model_by_alias=False, tags=["documents"])(self.analyze)
        self.router.get("/AnalyzeProject/{project_id}", response_model_by_alias=False, tags=["documents"])(self.analyze_project)
        self.router.get("/Analyze/{project_id}/{document_id}/report", tags=["documents"])(self.download_report)
        self.router.get("/GetVariable/{project_id}/{document_id}", tags=["documents"])(self.get_variable)
        self.router.delete("/DeleteDocument/{project_id}/{document_id}", tags=["documents"])(self.delete_document)
        self.router.post("/UpdateExtraction/{project_id}", tags=["documents"])(self.update_extraction)
        self.router.post("/GenerateReports/{project_id}", tags=["documents"])(self.generate_reports)
        self.router.put("/UpdateReports/{project_id}", tags=["documents"])(self.update_reports)

    async def upload_document(
        self,
        project_id: int,
        file: UploadFile = File(...),
        document_type: DocumentCategory = Form(...),
    ):
        if not file.filename:
            raise HTTPException(400, "No filename provided")
        contents = await file.read()
        try:
            return container.document_service.upload_document(
                project_id, file.filename, contents, document_type
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except DocumentExistsError as exc:
            raise HTTPException(409, str(exc)) from exc
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def analyze(self, project_id: int, document_id: str):
        try:
            return container.document_service.analyze_document(project_id, document_id)
        except (InvalidSlugError, ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def analyze_project(self, project_id: int):
        try:
            metadata, aggregated = container.project_service.aggregate_project_data(project_id, auto_analyze=True)
            return container.document_service._build_extraction_response(
                project_id, "project_batch", aggregated
            )
        except (InvalidSlugError, ProjectNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def download_report(self, project_id: int, document_id: str):
        try:
            document = self.storage.get_document(project_id, document_id)
            content = self.storage.read_spec_json(project_id, document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        headers = {
            "Content-Disposition": f'attachment; filename="{document_id}_{document.ToolID}.json"'
        }
        return Response(content=content, media_type="application/json", headers=headers)

    def get_variable(self, project_id: int, document_id: str, categories: str = None):
        try:
            return container.document_service.get_variables(project_id, document_id, categories)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (InvalidSlugError, ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def delete_document(self, project_id: int, document_id: str):
        try:
            self.storage.delete_document(project_id, document_id)
            from source.utils.embedder import VectorStoreManager
            # Remove the document's chunks from every category store that exists
            all_store_paths = self.storage.all_vectorstore_paths(project_id)
            for slug, store_path in all_store_paths.items():
                try:
                    vs = VectorStoreManager(store_path)
                    removed = vs.remove_document(document_id)
                    if removed:
                        logger.info(
                            "Removed %d chunks for document %s from %s store",
                            removed, document_id, slug,
                        )
                except Exception as exc:
                    logger.warning(
                        "Could not clean up vector store '%s' for document %s: %s",
                        slug, document_id, exc,
                    )
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {"Status": "success", "Message": f"Document {document_id} deleted"}

    def update_extraction(self, project_id: int, request: dict = Body(...)):
        from source.schemas.project import UpdateExtractionRequest
        from source.schemas.project import UpdateExtractionRequest
        from source.schemas.secsgem import EquipmentSpec, StatusVariable, DataVariable, Event, Alarm, RemoteCommand, State, StateTransition
        from source.schemas.report import ReportDefinition
        
        try:
            # Validate payload using new schema
            validated_req = UpdateExtractionRequest(**request)
            
            self.storage.increment_project_version(project_id)
            json_path = self.storage.spec_json_path(project_id, "project_batch")
            
            # Read existing EquipmentSpec (which holds ToolID/ToolType securely)
            try:
                spec_json = self.storage.read_spec_json(project_id, "project_batch")
                spec_obj = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                spec_obj = EquipmentSpec(ToolID="", ToolType="")
                
            # Map fields back to EquipmentSpec format
            spec_obj.StatusVariables = [
                StatusVariable(
                    SVID=sv.SVID, Name=sv.Name, Description=sv.Description,
                    DataType=sv.DataType, AccessType=sv.AccessType
                ) for sv in validated_req.StatusVariables
            ]
            
            spec_obj.DataVariables = [
                DataVariable(
                    DvID=dv.DvID, Name=dv.Name, Unit=dv.Unit, ValueType=dv.ValueType
                ) for dv in validated_req.DataVariables
            ]
            
            spec_obj.Events = [
                Event(
                    CEID=e.CEID, Name=e.EventName, Description=e.Description
                ) for e in validated_req.Events
            ]
            
            spec_obj.Alarms = [
                Alarm(
                    AlarmID=a.AlarmID, Name=a.AlarmText, Severity=a.Severity
                ) for a in validated_req.Alarms
            ]
            
            spec_obj.RemoteCommands = [
                RemoteCommand(
                    RCMD=rc.RCMD, Description=rc.Description, Parameters=rc.Parameters
                ) for rc in validated_req.RemoteCommands
            ]
            
            spec_obj.States = [State(**s) for s in validated_req.States]
            spec_obj.StateTransitions = [StateTransition(**st) for st in validated_req.StateTransitions]
            spec_obj.Reports = [ReportDefinition(**r) for r in validated_req.Reports]
            
            self.storage.save_spec_json(json_path, spec_obj)
            return {"Status": "success", "Message": "Extraction updated successfully"}
            
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def generate_reports(self, project_id: int):
        from source.schemas.secsgem import EquipmentSpec
        try:
            self.storage.increment_project_version(project_id)
            json_path = self.storage.spec_json_path(project_id, "project_batch")
            try:
                spec_json = self.storage.read_spec_json(project_id, "project_batch")
                spec_obj = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                _, spec_obj = container.project_service.aggregate_project_data(project_id)
            
            reports = container.report_service.generate_synthetic_reports(spec_obj)
            spec_obj.Reports = reports
            self.storage.save_spec_json(json_path, spec_obj)
            
            return container.document_service._build_extraction_response(
                project_id, "project_batch", spec_obj
            )
        except (InvalidSlugError, ProjectNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def update_reports(self, project_id: int, request: dict = Body(...)):
        from source.schemas.secsgem import EquipmentSpec
        from source.schemas.report import ReportDefinition
        
        try:
            reports_data = request.get("Reports", [])
            reports = [ReportDefinition(**r) for r in reports_data]
            
            self.storage.increment_project_version(project_id)
            json_path = self.storage.spec_json_path(project_id, "project_batch")
            try:
                spec_json = self.storage.read_spec_json(project_id, "project_batch")
                spec_obj = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                _, spec_obj = container.project_service.aggregate_project_data(project_id)
            
            spec_obj.Reports = reports
            self.storage.save_spec_json(json_path, spec_obj)
            
            return container.document_service._build_extraction_response(
                project_id, "project_batch", spec_obj
            )
        except Exception as exc:
            raise HTTPException(400, f"Error updating reports: {str(exc)}")