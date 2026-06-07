import io
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Tuple

from pypdf import PdfReader

from source.schemas.secsgem import EquipmentSpec

logger = logging.getLogger(__name__)


class DocumentProcessingStrategy(ABC):
    """Abstract base class for document processing strategies."""

    @abstractmethod
    def get_pages(self, contents: bytes) -> int:
        """Resolve the page or sheet count from the document contents."""
        pass

    @abstractmethod
    def analyze(
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> Tuple[EquipmentSpec, list[tuple[int, str]]]:
        """Perform parsing and analysis of the document, returning the spec and document pages."""
        pass

    def post_upload(
        self, project_id: int, filename: str, contents: bytes, storage: Any
    ) -> None:
        """Post-upload hook to perform additional actions (e.g. copying files)."""
        pass


class PdfProcessingStrategy(DocumentProcessingStrategy):
    """Strategy for processing PDF documents."""

    def get_pages(self, contents: bytes) -> int:
        return len(PdfReader(io.BytesIO(contents)).pages)

    def analyze(
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> Tuple[EquipmentSpec, list[tuple[int, str]]]:
        pages = container.parser.extract_pages(str(file_path))
        if not pages:
            raise ValueError("Could not extract any text from the PDF")

        doc_text = "\n".join(t for _, t in pages)

        tables_dir = storage.extracted_tables_path(project_id)
        tables_store_path = storage.vectorstore_path_for_category(project_id, "tables")
        spec = container.extractor.extract(
            doc_text,
            pdf_path=file_path,
            tables_dir=tables_dir,
            tables_store_path=tables_store_path,
        )

        try:
            reports = container.report_service.generate_synthetic_reports(spec)
            spec.Reports = reports
        except Exception as exc:
            logger.error("Report generation failed for %s/%s (non-fatal): %s", project_id, document_id, exc)
            spec.Reports = []

        if hasattr(document, "DocumentType") and document.DocumentType:
            doc_type_val = document.DocumentType.value if hasattr(document.DocumentType, "value") else str(document.DocumentType)
            spec.DocumentType = doc_type_val

        return spec, pages


class ExcelProcessingStrategy(DocumentProcessingStrategy):
    """Strategy for processing Excel documents."""

    def get_pages(self, contents: bytes) -> int:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(contents), read_only=True)
        pages = len(wb.sheetnames)
        wb.close()
        return pages

    def analyze(
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> Tuple[EquipmentSpec, list[tuple[int, str]]]:
        spec = container.extractor.extract_excel(file_path)
        if not spec.ToolID:
            project_meta = storage.get_project(project_id)
            spec.ToolID = project_meta.ProjectName
            spec.ToolType = project_meta.Tool.value or "Semiconductor Processing Equipment"
        spec.Reports = []

        if hasattr(document, "DocumentType") and document.DocumentType:
            doc_type_val = document.DocumentType.value if hasattr(document.DocumentType, "value") else str(document.DocumentType)
            spec.DocumentType = doc_type_val

        return spec, []


class TextProcessingStrategy(DocumentProcessingStrategy):
    """Strategy for processing text/SML script documents."""

    def get_pages(self, contents: bytes) -> int:
        return 1

    def analyze(
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> Tuple[EquipmentSpec, list[tuple[int, str]]]:
        project_meta = storage.get_project(project_id)
        doc_type_val = "SML Scripts"
        if hasattr(document, "DocumentType") and document.DocumentType:
            doc_type_val = document.DocumentType.value if hasattr(document.DocumentType, "value") else str(document.DocumentType)

        spec = EquipmentSpec(
            DocumentType=doc_type_val,
            ToolID=project_meta.ProjectName,
            ToolType=project_meta.Tool.value or "Semiconductor Processing Equipment",
        )
        spec.Reports = []
        return spec, []

    def post_upload(
        self, project_id: int, filename: str, contents: bytes, storage: Any
    ) -> None:
        tool_char_dir = storage._project_dir(project_id) / storage.TOOL_CHAR_DIR
        tool_char_dir.mkdir(parents=True, exist_ok=True)
        dst_path = tool_char_dir / filename
        dst_path.write_bytes(contents)
        logger.info("Copied SML script %s to %s", filename, dst_path)


class DocumentProcessorFactory:
    """Factory to resolve the document processing strategy by file extension."""

    @staticmethod
    def get_strategy(filename: str) -> DocumentProcessingStrategy:
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return PdfProcessingStrategy()
        elif ext == ".xlsx":
            return ExcelProcessingStrategy()
        elif ext == ".txt":
            return TextProcessingStrategy()
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
