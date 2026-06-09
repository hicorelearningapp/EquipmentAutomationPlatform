import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Body
from fastapi.responses import Response

from source.managers.service_container import container
from source.schemas.project import DocumentCategory, GenerateReportsRequest
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
            from source.schemas.secsgem import EquipmentSpec
            metadata = self.storage.get_project(project_id)
            has_pending = any(doc.Status == "uploaded" for doc in metadata.Documents)

            if has_pending:
                metadata, aggregated = container.project_service.aggregate_project_data(project_id, auto_analyze=True)
                self.storage.save_spec_json(self.storage.spec_json_path(project_id, "project_batch"), aggregated)
                return container.document_service._build_extraction_response(
                    project_id, "project_batch", aggregated
                )
            else:
                try:
                    spec_json = self.storage.read_spec_json(project_id, "project_batch")
                    spec_obj = EquipmentSpec.model_validate_json(spec_json)
                    return container.document_service._build_extraction_response(
                        project_id, "project_batch", spec_obj
                    )
                except Exception:
                    metadata, aggregated = container.project_service.aggregate_project_data(project_id, auto_analyze=True)
                    self.storage.save_spec_json(self.storage.spec_json_path(project_id, "project_batch"), aggregated)
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
        from source.schemas.secsgem import EquipmentSpec, StatusVariable, DataVariable, Event, Alarm, RemoteCommand, State, StateTransition
        from source.schemas.report import ReportDefinition
        from pydantic import ValidationError
        
        try:
            # Validate payload using new schema
            try:
                validated_req = UpdateExtractionRequest(**request)
            except ValidationError as ve:
                raise HTTPException(422, f"Payload validation failed: {ve}")
            
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
                    DataType=sv.DataType, AccessType=sv.AccessType,
                    Value=sv.Value, Confidence=sv.Confidence
                ) for sv in validated_req.StatusVariables
            ]
            
            spec_obj.DataVariables = [
                DataVariable(
                    DvID=dv.DvID, Name=dv.Name, Unit=dv.Unit, ValueType=dv.ValueType
                ) for dv in validated_req.DataVariables
            ]
            
            spec_obj.Events = [
                Event(
                    CEID=e.CEID, Name=e.EventName, Description=e.Description,
                    LinkedVIDs=e.LinkedVIDs, LinkedReports=e.LinkedReports,
                    Confidence=e.Confidence
                ) for e in validated_req.Events
            ]
            
            spec_obj.Alarms = [
                Alarm(
                    AlarmID=a.AlarmID, Name=a.AlarmName, Severity=a.Severity,
                    LinkedVID=a.LinkedVID, Description=a.Description,
                    Confidence=a.Confidence
                ) for a in validated_req.Alarms
            ]
            
            spec_obj.RemoteCommands = [
                RemoteCommand(
                    RCMD=rc.RCMD, Description=rc.Description, Parameters=rc.Parameters,
                    Confidence=rc.Confidence
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

    def generate_reports(self, project_id: int, request: GenerateReportsRequest = Body(default_factory=GenerateReportsRequest)):
        from source.schemas.secsgem import EquipmentSpec
        try:
            self.storage.increment_project_version(project_id)
            json_path = self.storage.spec_json_path(project_id, "project_batch")
            try:
                spec_json = self.storage.read_spec_json(project_id, "project_batch")
                spec_obj = EquipmentSpec.model_validate_json(spec_json)
            except Exception:
                _, spec_obj = container.project_service.aggregate_project_data(project_id)
            
            if request.ceids:
                target_events = [e for e in spec_obj.Events if e.CEID in request.ceids]
                original_events = spec_obj.Events
                spec_obj.Events = target_events
                
                new_reports = container.report_service.generate_synthetic_reports(spec_obj)
                
                spec_obj.Events = original_events
                
                # Merge logic: just keep all existing reports that don't have clashing RPTIDs
                new_rptids = {r.RPTID for r in new_reports}
                kept_reports = [r for r in spec_obj.Reports if r.RPTID not in new_rptids]
                
                spec_obj.Reports = kept_reports + new_reports
            else:
                reports = container.report_service.generate_synthetic_reports(spec_obj)
                spec_obj.Reports = reports
                
            # Deterministically re-link events to reports based on LinkedVIDs overlap
            for event in spec_obj.Events:
                if not event.LinkedVIDs:
                    event.LinkedReports = []
                    continue
                
                uncovered = set(event.LinkedVIDs)
                chosen_rptids = set()
                
                # Greedy set cover to minimize redundant variables
                while uncovered:
                    best_report = None
                    best_cover_count = 0
                    best_extra_count = float('inf')
                    
                    for report in spec_obj.Reports:
                        if report.RPTID in chosen_rptids:
                            continue
                            
                        rpt_vids = set(report.LinkedVIDs)
                        covered = uncovered.intersection(rpt_vids)
                        extra = rpt_vids - set(event.LinkedVIDs)
                        
                        cover_count = len(covered)
                        extra_count = len(extra)
                        
                        if cover_count > best_cover_count:
                            best_cover_count = cover_count
                            best_extra_count = extra_count
                            best_report = report
                        elif cover_count == best_cover_count and cover_count > 0:
                            if extra_count < best_extra_count:
                                best_extra_count = extra_count
                                best_report = report
                                
                    if best_report is None:
                        break
                        
                    chosen_rptids.add(best_report.RPTID)
                    uncovered -= set(best_report.LinkedVIDs)
                    
                event.LinkedReports = sorted(list(chosen_rptids))
                
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