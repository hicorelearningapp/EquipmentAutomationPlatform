import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas.project import DocumentMetadata, ProjectMetadata, ProjectCreate, ProjectOut
from app.schemas.mapping import ProjectMapping
from app.schemas.secsgem import EquipmentSpec

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class InvalidSlugError(StorageError):
    pass


class ProjectExistsError(StorageError):
    pass


class ProjectNotFoundError(StorageError):
    pass


class DocumentNotFoundError(StorageError):
    pass


class StorageService:
    DOCUMENTS_DIR = "Documents"
    MESTAG_DIR = "MESTagDocuments"
    EXTRACTED_JSON_DIR = "ExtractedJson"
    VECTORSTORE_DIR = "Vectorstore"
    METADATA_DIR = "Metadata"
    CODE_DIR = "Code"
    METADATA_FILE = "project.json"

    _SLUG_RE = re.compile(r"[^a-z0-9]+")

    def __init__(self, storage_root: str | Path | None = None) -> None:
        if storage_root is None:
            storage_root = settings.EAP_STORAGE_ROOT
        if not str(storage_root).strip():
            raise StorageError("EAP_STORAGE_ROOT must be set")
        self.root = self._resolve_root(storage_root)
        self._ensure_root()

    def _get_next_id(self) -> int:
        ids = []
        for child in self.root.iterdir():
            if child.is_dir() and child.name.isdigit():
                ids.append(int(child.name))
        return max(ids) + 1 if ids else 1

    @classmethod
    def slugify(cls, value: str, fallback: str = "item") -> str:
        slug = cls._SLUG_RE.sub("_", value.strip().lower()).strip("_")
        return slug or fallback

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def create_project(self, project_create: ProjectCreate) -> ProjectOut:
        project_id = self._get_next_id()
        self._ensure_project_dirs(project_id)
        
        now = self.now()
        metadata = ProjectOut(
            ProjectID=project_id,
            ProjectName=project_create.ProjectName,
            ProjectVersion="1.0",
            VendorName=project_create.VendorName,
            Tool=project_create.Tool,
            CreatedAt=now,
            LastUpdatedOn=now,
            Status="active",
        )
        self._write_metadata(metadata)
        return metadata

    def register_document(
        self,
        project_id: int,
        document_id: str,
        document_type: str,
        filename: str,
        file_size: float,
        pages: int,
    ) -> DocumentMetadata:
        metadata = self.get_project(project_id)
        project_dir = self._project_dir(project_id)
        pdf_path = self.document_pdf_path(project_id, document_id)
        json_path = self.spec_json_path(project_id, document_id)

        document = DocumentMetadata(
            DocumentID=document_id,
            DocumentType=document_type,
            FileName=filename,
            FileSize=file_size,
            Pages=pages,
            UploadDate=self.now(),
            UploadedBy="",
            Status="uploaded",
        )

        Documents = [doc for doc in metadata.Documents if doc.DocumentID != document_id]
        Documents.append(document)
        metadata.Documents = sorted(Documents, key=lambda doc: doc.UploadDate)
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return document

    def complete_extraction(
        self,
        project_id: int,
        document_id: str,
        spec: EquipmentSpec,
    ) -> DocumentMetadata:
        metadata = self.get_project(project_id)

        for doc in metadata.Documents:
            if doc.DocumentID == document_id:
                doc.Status = "completed"
                if spec.DocumentType:
                    doc.DocumentType = spec.DocumentType
                document = doc
                break
        else:
            raise DocumentNotFoundError(
                f"Document '{document_id}' was not found in project '{project_id}'"
            )

        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return document

    def mark_failed(self, project_id: int, document_id: str) -> DocumentMetadata:
        metadata = self.get_project(project_id)

        for doc in metadata.Documents:
            if doc.DocumentID == document_id:
                doc.Status = "failed"
                document = doc
                break
        else:
            raise DocumentNotFoundError(
                f"Document '{document_id}' was not found in project '{project_id}'"
            )

        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return document

    def list_projects(self) -> list[ProjectOut]:
        projects: list[ProjectOut] = []
        for child in self.root.iterdir():
            if not child.is_dir() or not child.name.isdigit():
                continue
            metadata_path = child / self.METADATA_DIR / self.METADATA_FILE
            if not metadata_path.exists():
                continue
            
            try:
                raw_data = json.loads(metadata_path.read_text(encoding="utf-8"))
                project = ProjectOut.model_validate(raw_data)
                projects.append(project)
            except Exception as e:
                logger.error(f"Error reading project at {child}: {e}")
                continue
                
        return sorted(projects, key=lambda p: p.ProjectID)

    def get_project(self, project_id: int) -> ProjectMetadata:
        metadata_path = self._metadata_path(project_id)
        if not metadata_path.exists():
            raise ProjectNotFoundError(f"Project '{project_id}' was not found")
        return self._read_metadata(metadata_path)

    def delete_project(self, project_id: int) -> None:
        project_dir = self._project_dir(project_id)
        if not self._metadata_path(project_id).exists():
            raise ProjectNotFoundError(f"Project '{project_id}' was not found")
        shutil.rmtree(project_dir)

    def increment_project_version(self, project_id: int) -> str:
        metadata = self.get_project(project_id)
        current_version = metadata.ProjectVersion or "1.0"
        
        try:
            parts = current_version.split(".")
            if len(parts) >= 2:
                # 2-tier logic: increment the second part
                major = parts[0]
                minor = int(parts[1]) + 1
                new_version = f"{major}.{minor}"
            else:
                # Fallback for non-standard versions
                new_version = f"{current_version}.1"
        except (ValueError, IndexError):
            new_version = "1.1"

        metadata.ProjectVersion = new_version
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        logger.info(f"Project {project_id} version bumped: {current_version} -> {new_version}")
        return new_version

    def update_project_metadata(self, project_id: int, update: Any) -> ProjectOut:
        metadata = self.get_project(project_id)
        
        if update.ProjectName is not None:
            metadata.ProjectName = update.ProjectName
        if update.VendorName is not None:
            metadata.VendorName = update.VendorName
        if update.Tool is not None:
            metadata.Tool = update.Tool
        if update.ProjectVersion is not None:
            metadata.ProjectVersion = update.ProjectVersion
            
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return ProjectOut.model_validate(metadata.model_dump())

    def delete_document(self, project_id: int, document_id: str) -> None:
        metadata = self.get_project(project_id)
        document = self.get_document(project_id, document_id)

        pdf_path = self._project_relative_path(project_id, document.DocumentPath)
        json_path = self._project_relative_path(project_id, document.JsonPath)
        if pdf_path.exists():
            pdf_path.unlink()
        if json_path.exists():
            json_path.unlink()

        metadata.Documents = [doc for doc in metadata.Documents if doc.DocumentID != document_id]
        metadata.DocumentCount = len(metadata.Documents)
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)

    def save_project_code(self, project_id: int, category: str, source_code: str) -> None:
        project_dir = self._project_dir(project_id)
        if not self._metadata_path(project_id).exists():
            raise ProjectNotFoundError(f"Project '{project_id}' was not found")
        
        code_dir = project_dir / self.CODE_DIR
        code_dir.mkdir(parents=True, exist_ok=True)
        
        code_file = code_dir / category
        code_file.write_text(source_code, encoding="utf-8")
        logger.info("Saved generated code to %s", code_file)

    def prepare_document_paths(
        self, project_id: int, original_filename: str
    ) -> tuple[str, Path, Path]:
        metadata = self.get_project(project_id)
        base_id = self.slugify(Path(original_filename).stem, fallback="document")
        existing_ids = {doc.DocumentID for doc in metadata.Documents}

        document_id = base_id
        counter = 2
        while (
            document_id in existing_ids
            or self.document_pdf_path(project_id, document_id).exists()
            or self.spec_json_path(project_id, document_id).exists()
        ):
            document_id = f"{base_id}_{counter}"
            counter += 1

        return (
            document_id,
            self.document_pdf_path(project_id, document_id),
            self.spec_json_path(project_id, document_id),
        )

    def save_pdf(self, pdf_path: Path, contents: bytes) -> None:
        self._assert_inside_root(pdf_path)
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(contents)

    def save_spec_json(self, json_path: Path, spec: EquipmentSpec) -> None:
        self._assert_inside_root(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(spec.model_dump_json(indent=4), encoding="utf-8")

    def add_document_metadata(
        self,
        project_id: int,
        document_id: str,
        document_type: str,
        original_filename: str,
        spec: EquipmentSpec,
        vector_indexed: bool,
        file_size: float = 0.0,
        pages: int = 0,
    ) -> DocumentMetadata:
        metadata = self.get_project(project_id)
        project_dir = self._project_dir(project_id)
        pdf_path = self.document_pdf_path(project_id, document_id)
        json_path = self.spec_json_path(project_id, document_id)

        document = DocumentMetadata(
            DocumentID=document_id,
            DocumentType=document_type,
            FileName=original_filename,
            FileSize=file_size,
            Pages=pages,
            UploadDate=self.now(),
            UploadedBy="",
            Status="completed",
        )

        Documents = [doc for doc in metadata.Documents if doc.DocumentID != document_id]
        Documents.append(document)
        metadata.Documents = sorted(Documents, key=lambda doc: doc.UploadDate)
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return document

    def get_document(self, project_id: int, document_id: str) -> DocumentMetadata:
        metadata = self.get_project(project_id)
        for document in metadata.Documents:
            if document.DocumentID == document_id:
                return document
        raise DocumentNotFoundError(
            f"Document '{document_id}' was not found in project '{project_id}'"
        )

    def get_mapping(self, project_id: int) -> ProjectMapping:
        path = self.mapping_path(project_id)
        if not path.exists():
            from app.schemas.mapping import ProjectMapping
            return ProjectMapping(ProjectID=project_id)
        try:
            from app.schemas.mapping import ProjectMapping
            return ProjectMapping.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            from app.schemas.mapping import ProjectMapping
            return ProjectMapping(ProjectID=project_id)

    def save_mapping(self, project_id: int, mapping: ProjectMapping) -> None:
        path = self.mapping_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(mapping.model_dump_json(indent=2), encoding="utf-8")

    def read_spec_json(self, project_id: int, document_id: str) -> str:
        self.get_document(project_id, document_id)
        path = self.spec_json_path(project_id, document_id)
        if not path.exists():
            raise DocumentNotFoundError(
                f"Extracted JSON for document '{document_id}' was not found"
            )
        return path.read_text(encoding="utf-8")

    def vectorstore_path(self, project_id: int) -> Path:
        self.get_project(project_id)
        return self._project_dir(project_id) / self.VECTORSTORE_DIR

    def mapping_path(self, project_id: int) -> Path:
        return self._project_dir(project_id) / self.METADATA_DIR / "mapping.json"

    def mes_tags_json_path(self, project_id: int, document_id: str) -> Path:
        return self._project_dir(project_id) / "MESTags" / f"{document_id}.json"

    def save_mes_tags(self, project_id: int, document_id: str, tags: list[dict]) -> None:
        path = self.mes_tags_json_path(project_id, document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(tags, indent=2), encoding="utf-8")

    def get_mes_tags(self, project_id: int, document_id: str) -> list[dict]:
        path = self.mes_tags_json_path(project_id, document_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def list_mes_tag_documents(self, project_id: int) -> list[str]:
        base_dir = self._project_dir(project_id) / "MESTags"
        if not base_dir.exists():
            return []
        return [f.stem for f in base_dir.glob("*.json")]

    def document_pdf_path(self, project_id: int, document_id: str) -> Path:
        return self._project_dir(project_id) / self.DOCUMENTS_DIR / f"{document_id}.pdf"

    def spec_json_path(self, project_id: int, document_id: str) -> Path:
        return (
            self._project_dir(project_id)
            / self.EXTRACTED_JSON_DIR
            / f"{document_id}.json"
        )

    def mes_tag_path(self, project_id: int, document_id: str) -> Path:
        self._validate_id(document_id)
        return (
            self._project_dir(project_id)
            / self.MESTAG_DIR
            / f"{document_id}.pdf"
        )

    def _resolve_root(self, storage_root: str | Path) -> Path:
        root = Path(storage_root).expanduser()
        if not root.is_absolute():
            logger.warning(
                "EAP_STORAGE_ROOT is relative (%s). Use an absolute path on Azure.",
                storage_root,
            )
            root = Path.cwd() / root
        return root.resolve()

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StorageError(f"Could not create EAP_STORAGE_ROOT at {self.root}") from exc

        if not self.root.is_dir():
            raise StorageError(f"EAP_STORAGE_ROOT is not a directory: {self.root}")

        probe = self.root / ".write_test"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise StorageError(f"EAP_STORAGE_ROOT is not writable: {self.root}") from exc

    def _ensure_project_dirs(self, project_id: int) -> None:
        project_dir = self._project_dir(project_id)
        for folder in (
            self.DOCUMENTS_DIR,
            self.MESTAG_DIR,
            self.EXTRACTED_JSON_DIR,
            self.VECTORSTORE_DIR,
            self.METADATA_DIR,
        ):
            path = project_dir / folder
            self._assert_inside_root(path)
            path.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: int) -> Path:
        path = (self.root / str(project_id)).resolve()
        self._assert_inside_root(path)
        return path

    def _metadata_path(self, project_id: int) -> Path:
        return self._project_dir(project_id) / self.METADATA_DIR / self.METADATA_FILE

    def _project_relative_path(self, project_id: int, relative_path: str) -> Path:
        if Path(relative_path).is_absolute():
            raise InvalidSlugError("Stored project paths must be relative")
        project_dir = self._project_dir(project_id)
        path = (project_dir / relative_path).resolve()
        if path != project_dir and project_dir not in path.parents:
            raise InvalidSlugError(f"Path escapes project storage: {relative_path}")
        return path

    def _read_metadata(self, path: Path) -> ProjectMetadata:
        try:
            return ProjectMetadata.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StorageError(f"Could not read project metadata at {path}") from exc

    def _write_metadata(self, metadata: ProjectOut | ProjectMetadata) -> None:
        self._ensure_project_dirs(metadata.ProjectID)
        path = self._metadata_path(metadata.ProjectID)
        payload = json.dumps(metadata.model_dump(mode="json"), indent=2)
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(payload + "\n", encoding="utf-8")
        temp_path.replace(path)

    def _validate_id(self, value: str) -> None:
        if value != self.slugify(value):
            raise InvalidSlugError(f"Invalid id: {value}")

    def _assert_inside_root(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise InvalidSlugError(f"Path escapes EAP_STORAGE_ROOT: {path}")
