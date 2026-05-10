import io

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pypdf import PdfReader

from app.config import settings
from app.managers.service_container import container
from app.schemas.project import DocumentType
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
        self.router = APIRouter(tags=["documents"])
        self.storage = StorageService()
        self.register_routes()

    def register_routes(self):
        self.router.post("/UploadDocument/{project_id}")(self.upload_document)
        self.router.get("/Analyze/{project_id}/{document_id}")(self.analyze)
        self.router.get("/Analyze/{project_id}/{document_id}/report")(self.download_report)
        self.router.delete("/DeleteDocument/{project_id}/{document_id}")(self.delete_document)

    async def upload_document(
        self,
        project_id: str,
        file: UploadFile = File(...),
        document_type: DocumentType = Form(...),
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
                document_type=document_type,
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
            "DocumentType": document_type,
            "FileName": document.FileName,
            "ToolType": tool_type,
            "Vendor": vendor,
            "Pages": document.Pages,
            "FileSize": document.FileSize,
        }

    def analyze(self, project_id: str, document_id: str):
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
            return self._build_extraction_response(project_id, document_id, spec)

        if document.Status == "failed":
            return self._build_failed_response(project_id, document_id)

        try:
            pdf_path = self.storage.document_pdf_path(project_id, document_id)
            text = container.parser.extract_text(str(pdf_path))
            if not text.strip():
                raise ValueError("Could not extract any text from the PDF")

            spec = container.extractor.extract(text)

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
        except Exception:
            self.storage.mark_failed(project_id, document_id)
            return self._build_failed_response(project_id, document_id)

        return self._build_extraction_response(project_id, document_id, spec)

    def _build_failed_response(self, project_id: str, document_id: str) -> dict:
        return {
            "ProjectID": project_id,
            "ExtractionId": document_id,
            "ConfidenceScore": 0.0,
            "ExtractionStatus": "failed",
            "StatusVariables": [],
            "DataVariables": [],
            "Events": [],
            "Alarms": [],
        }

    def _build_extraction_response(
        self, project_id: str, document_id: str, spec: EquipmentSpec
    ) -> dict:
        all_confidences = (
            [v.confidence for v in spec.variables]
            + [e.confidence for e in spec.events]
            + [a.confidence for a in spec.alarms]
        )
        overall_confidence = (
            sum(all_confidences) / len(all_confidences) if all_confidences else 0.0
        )

        return {
            "ProjectID": project_id,
            "ExtractionId": document_id,
            "ConfidenceScore": round(overall_confidence, 3),
            "ExtractionStatus": "completed",
            "StatusVariables": [
                {
                    "SVID": v.vid,
                    "Name": v.name,
                    "Description": v.description or "",
                    "DataType": v.type,
                    "AccessType": v.access,
                    "Value": "",
                    "Confidence": v.confidence,
                }
                for v in spec.variables if v.category == "SV"
            ],
            "DataVariables": [
                {
                    "DvID": v.vid,
                    "Name": v.name,
                    "Unit": v.unit or "",
                    "ValueType": v.type,
                }
                for v in spec.variables if v.category == "DV"
            ],
            "Events": [
                {
                    "CEID": e.ceid,
                    "EventName": e.name,
                    "Description": e.description or "",
                }
                for e in spec.events
            ],
            "Alarms": [
                {
                    "AlarmId": a.alarm_id,
                    "AlarmText": a.name,
                    "Severity": a.severity,
                }
                for a in spec.alarms
            ],
        }

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
            "Content-Disposition": f'attachment; filename="{document_id}_{document.ToolId}.json"'
        }
        return Response(content=content, media_type="application/json", headers=headers)

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
