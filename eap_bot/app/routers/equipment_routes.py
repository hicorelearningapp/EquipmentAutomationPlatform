import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pypdf import PdfReader

from app.config import settings
from app.managers.service_container import container
from app.schemas.secsgem import EquipmentSpec
from app.services.storage_service import (
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)
from app.utils.embedder import VectorStoreManager


class EquipmentAPI:
    def __init__(self):
        self.router = APIRouter(
            prefix="/projects/{project_id}", tags=["documents"]
        )
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/upload")(self.upload)
        self.router.get("/documents/{document_id}/extract")(self.extract)
        self.router.get("/documents/{document_id}/extract/report")(self.download_report)
        self.router.get("/documents/{document_id}/extract/status_variables")(self.status_variables)
        self.router.get("/documents/{document_id}/extract/data_variable")(self.data_variables)
        self.router.get("/documents/{document_id}/extract/events")(self.get_events)
        self.router.get("/documents/{document_id}/extract/alarms")(self.get_alarms)
        self.router.delete("/documents/{document_id}")(self.delete_document)

    async def upload(
        self,
        project_id: str,
        file: UploadFile = File(...),
        tool_type: str = Form(""),
        vendor: str = Form(""),
    ):
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Only .pdf files are accepted")

        contents = await file.read()
        if len(contents) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(400, "File exceeds MAX_UPLOAD_SIZE")

        file_size = float(len(contents))
        pages = len(PdfReader(io.BytesIO(contents)).pages)

        try:
            document_id, pdf_path, _ = self.storage.prepare_document_paths(
                project_id, file.filename
            )
            self.storage.save_pdf(pdf_path, contents)
            document = self.storage.register_document(
                project_id=project_id,
                document_id=document_id,
                filename=file.filename,
                file_size=file_size,
                pages=pages,
            )
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except ProjectNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return {
            "Status": "uploaded",
            "DocumentID": document_id,
            "FileName": document.FileName,
            "ToolType": tool_type,
            "Vendor": vendor,
            "Pages": document.Pages,
            "FileSize": document.FileSize,
        }

    def extract(self, project_id: str, document_id: str):
        try:
            document = self.storage.get_document(project_id, document_id)
        except (InvalidSlugError, ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        if document.Status == "completed":
            try:
                spec_json = self.storage.read_spec_json(project_id, document_id)
                spec = EquipmentSpec.model_validate_json(spec_json)
            except StorageError as exc:
                raise HTTPException(500, str(exc)) from exc
            return self._build_extraction_response(project_id, document_id, spec.tool_id, spec)

        pdf_path = self.storage.document_pdf_path(project_id, document_id)
        text = container.parser.extract_text(str(pdf_path))
        if not text.strip():
            raise HTTPException(400, "Could not extract any text from the PDF")

        spec = container.extractor.extract(text)

        try:
            json_path = self.storage.spec_json_path(project_id, document_id)
            self.storage.save_spec_json(json_path, spec)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            vector_indexed = vector_store.add_document(
                text,
                metadata={
                    "project_id": project_id,
                    "document_id": document_id,
                    "tool_id": spec.tool_id,
                },
            )
            self.storage.complete_extraction(
                project_id=project_id,
                document_id=document_id,
                spec=spec,
                vector_indexed=vector_indexed,
            )
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

        return self._build_extraction_response(project_id, document_id, spec.tool_id, spec)

    def _build_extraction_response(
        self, project_id: str, document_id: str, tool_id: str, spec: EquipmentSpec
    ) -> dict:
        all_confidences = (
            [v.confidence for v in spec.variables]
            + [e.confidence for e in spec.events]
            + [a.confidence for a in spec.alarms]
        )
        overall_confidence = (
            sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        )
        confidence_level = (
            "High" if overall_confidence > 0.8
            else "Medium" if overall_confidence > 0.5
            else "Low"
        )

        return {
            "ExtractedFiles": [
                {
                    "Status": "completed",
                    "ProjectID": project_id,
                    "DocumentID": document_id,
                    "ToolID": tool_id,
                    "StatusVariablesCount": sum(1 for v in spec.variables if v.category == "SV"),
                    "DataVariablesCount": sum(1 for v in spec.variables if v.category == "DV"),
                    "EventsCount": len(spec.events),
                    "AlarmsCount": len(spec.alarms),
                    "OverallConfidence": round(overall_confidence, 3),
                    "ConfidenceLevel": confidence_level,
                    "Spec": spec.model_dump(),
                }
            ]
        }

    def _load_spec(self, project_id: str, document_id: str) -> EquipmentSpec:
        try:
            document = self.storage.get_document(project_id, document_id)
            if document.Status != "completed":
                raise HTTPException(
                    400, "Document has not been extracted yet. Call the /extract endpoint first."
                )
            spec_json = self.storage.read_spec_json(project_id, document_id)
            return EquipmentSpec.model_validate_json(spec_json)
        except HTTPException:
            raise
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc

    def download_report(self, project_id: str, document_id: str):
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
            "Content-Disposition": f'attachment; filename="{document_id}_{document.tool_id}.json"'
        }
        return Response(content=content, media_type="application/json", headers=headers)

    def status_variables(self, project_id: str, document_id: str):
        spec = self._load_spec(project_id, document_id)
        return {
            "StatusVariables": [
                {
                    "SVId": v.vid,
                    "Name": v.name,
                    "Description": v.description or "",
                    "DataType": v.type,
                    "AccessType": v.access,
                    "Value": "",
                    "Confidence": v.confidence,
                }
                for v in spec.variables
                if v.category == "SV"
            ]
        }

    def data_variables(self, project_id: str, document_id: str):
        spec = self._load_spec(project_id, document_id)
        return {
            "DataVariables": [
                {
                    "DvID": v.vid,
                    "Name": v.name,
                    "Unit": v.unit or "",
                    "ValueType": v.type,
                }
                for v in spec.variables
                if v.category == "DV"
            ]
        }

    def get_events(self, project_id: str, document_id: str):
        spec = self._load_spec(project_id, document_id)
        return {
            "EventsList": [
                {
                    "CEID": e.ceid,
                    "EventName": e.name,
                    "Description": e.description or "",
                }
                for e in spec.events
            ]
        }

    def get_alarms(self, project_id: str, document_id: str):
        spec = self._load_spec(project_id, document_id)
        return {
            "AlarmsLst": [
                {
                    "AlarmId": a.alarm_id,
                    "AlarmText": a.name,
                    "Severity": a.severity,
                }
                for a in spec.alarms
            ]
        }

    def delete_document(self, project_id: str, document_id: str):
        try:
            self.storage.delete_document(project_id, document_id)
            vector_store = VectorStoreManager(self.storage.vectorstore_path(project_id))
            vector_store.remove_document(document_id)
        except InvalidSlugError as exc:
            raise HTTPException(400, str(exc)) from exc
        except (ProjectNotFoundError, DocumentNotFoundError) as exc:
            raise HTTPException(404, str(exc)) from exc
        except StorageError as exc:
            raise HTTPException(500, str(exc)) from exc
        return {
            "Status": "success",
            "Message": f"Document {document_id} deleted",
        }
