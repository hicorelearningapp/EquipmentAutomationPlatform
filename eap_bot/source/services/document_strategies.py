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
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> None:
        """Post-upload hook to perform additional actions (e.g. copying files)."""
        pass


class PdfProcessingStrategy(DocumentProcessingStrategy):
    """Strategy for processing PDF documents."""

    def get_pages(self, contents: bytes) -> int:
        return len(PdfReader(io.BytesIO(contents)).pages)

    def post_upload(
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> None:
        logger.info("Running pre-index and table extraction for %s", document.FileName)
        pages = container.parser.extract_pages(str(file_path))
        if pages:
            from source.utils.embedder import VectorStoreManager
            category_slug = storage._doc_category_to_slug(document.DocumentType)
            category_store_path = storage.vectorstore_path_for_category(project_id, category_slug)
            
            project_meta = storage.get_project(project_id)
            tool_id = project_meta.ProjectName
            
            vector_store = VectorStoreManager(category_store_path)
            vector_store.add_pages(
                pages,
                base_metadata={
                    "project_id": project_id,
                    "document_id": document_id,
                    "document_name": document.FileName,
                    "document_category": category_slug,
                    "tool_id": tool_id,
                },
            )

        tables_dir = storage.extracted_tables_path(project_id)
        tables_store_path = storage.vectorstore_path_for_category(project_id, "tables")
        section_csvs = container.extractor.extract_and_save_tables(
            pdf_path=file_path,
            tables_dir=tables_dir,
            tables_store_path=tables_store_path,
        )

        doc_text = "\n".join(t for _, t in pages)
        cache_dir = storage._project_dir(project_id) / "cache" / document_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "doc_text.txt").write_text(doc_text, encoding="utf-8")
        
        import json
        (cache_dir / "section_csvs.json").write_text(json.dumps(section_csvs), encoding="utf-8")

    def analyze(
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> Tuple[EquipmentSpec, list[tuple[int, str]]]:
        cache_dir = storage._project_dir(project_id) / "cache" / document_id
        doc_text_path = cache_dir / "doc_text.txt"
        section_csvs_path = cache_dir / "section_csvs.json"

        import json
        if doc_text_path.exists():
            doc_text = doc_text_path.read_text(encoding="utf-8")
            section_csvs = json.loads(section_csvs_path.read_text(encoding="utf-8")) if section_csvs_path.exists() else {}
        else:
            pages = container.parser.extract_pages(str(file_path))
            if not pages:
                raise ValueError("Could not extract any text from the PDF")
            doc_text = "\n".join(t for _, t in pages)
            tables_dir = storage.extracted_tables_path(project_id)
            tables_store_path = storage.vectorstore_path_for_category(project_id, "tables")
            section_csvs = container.extractor.extract_and_save_tables(
                pdf_path=file_path,
                tables_dir=tables_dir,
                tables_store_path=tables_store_path,
            )

        spec = container.extractor.extract(
            doc_text,
            section_csvs=section_csvs,
        )

        try:
            reports = container.report_service.generate_synthetic_reports(spec)
            spec.Reports = reports
        except Exception as exc:
            logger.error("Report generation failed for %s/%s (non-fatal): %s", project_id, document_id, exc)
            spec.Reports = []

        # Extract verbatim SML message samples into ToolCharacterization/base_script.txt.
        try:
            sml_text = container.extractor.extract_sml_scripts(doc_text)
            if sml_text:
                storage.upsert_base_script(project_id, document.FileName, sml_text)
        except Exception as exc:
            logger.error("SML script extraction failed for %s/%s (non-fatal): %s", project_id, document_id, exc)

        if hasattr(document, "DocumentType") and document.DocumentType:
            doc_type_val = document.DocumentType.value if hasattr(document.DocumentType, "value") else str(document.DocumentType)
            spec.DocumentType = doc_type_val

        return spec, []


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
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> None:
        tool_char_dir = storage._project_dir(project_id) / storage.TOOL_CHAR_DIR
        tool_char_dir.mkdir(parents=True, exist_ok=True)
        dst_path = tool_char_dir / document.FileName
        dst_path.write_bytes(file_path.read_bytes())
        logger.info("Copied SML script %s to %s", document.FileName, dst_path)


class LogFileProcessingStrategy(DocumentProcessingStrategy):
    """Strategy for SECS/GEM communication logs. RAG indexing only."""

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
        doc_type_val = "Log Files"
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
        self,
        project_id: int,
        document_id: str,
        document: Any,
        file_path: Path,
        storage: Any,
        container: Any,
    ) -> None:
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            if not content.strip():
                return

            from source.utils.embedder import VectorStoreManager

            category_slug = storage._doc_category_to_slug(document.DocumentType)
            store_path = storage.vectorstore_path_for_category(project_id, category_slug)
            project_meta = storage.get_project(project_id)
            vs = VectorStoreManager(store_path)
            vs.add_document(
                content,
                metadata={
                    "project_id": project_id,
                    "document_id": document_id,
                    "document_name": document.FileName,
                    "document_category": category_slug,
                    "tool_id": project_meta.ProjectName,
                },
            )
            logger.info("Indexed log file %s into RAG store at %s", document.FileName, store_path)
        except Exception as e:
            logger.warning("Failed to index log file %s: %s", document.FileName, e)


class DocumentProcessorFactory:
    """Factory to resolve the document processing strategy by file extension."""

    @staticmethod
    def get_strategy(filename: str, doc_category=None) -> DocumentProcessingStrategy:
        from source.schemas.project import DocumentCategory

        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return PdfProcessingStrategy()
        elif ext == ".xlsx":
            return ExcelProcessingStrategy()
        elif ext == ".txt":
            if doc_category == DocumentCategory.LOG_FILES or (
                hasattr(doc_category, "value") and doc_category.value == "Log Files"
            ):
                return LogFileProcessingStrategy()
            return TextProcessingStrategy()
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
