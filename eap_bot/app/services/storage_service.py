import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings
from app.schemas.project import DocumentMetadata, ProjectMetadata
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
    EXTRACTED_JSON_DIR = "ExtractedJson"
    VECTORSTORE_DIR = "Vectorstore"
    METADATA_DIR = "Metadata"
    METADATA_FILE = "project.json"

    _SLUG_RE = re.compile(r"[^a-z0-9]+")

    def __init__(self, storage_root: str | Path | None = None) -> None:
        if storage_root is None:
            storage_root = settings.EAP_STORAGE_ROOT
        if not str(storage_root).strip():
            raise StorageError("EAP_STORAGE_ROOT must be set")
        self.root = self._resolve_root(storage_root)
        self._ensure_root()

    @classmethod
    def slugify(cls, value: str, fallback: str = "item") -> str:
        slug = cls._SLUG_RE.sub("_", value.strip().lower()).strip("_")
        return slug or fallback

    @staticmethod
    def now() -> datetime:
        return datetime.now(timezone.utc)

    def create_project(
        self,
        project_name: str,
        vendor_name: str,
        tool: str,
        project_version: str = "1.0",
    ) -> ProjectMetadata:
        display_name = project_name.strip()
        if not display_name:
            raise InvalidSlugError("Project name cannot be empty")

        project_id = self.slugify(display_name, fallback="project")
        project_dir = self._project_dir(project_id)
        metadata_path = self._metadata_path(project_id)

        if metadata_path.exists():
            raise ProjectExistsError(
                f"A project named '{project_name}' already exists as '{project_id}'"
            )
        if project_dir.exists() and any(project_dir.iterdir()):
            raise ProjectExistsError(
                f"Project folder '{project_dir}' already exists but has no metadata file"
            )

        self._ensure_project_dirs(project_id)
        now = self.now()
        metadata = ProjectMetadata(
            ProjectID=project_id,
            ProjectName=display_name,
            VendorName=vendor_name,
            Tool=tool,
            ProjectVersion=project_version,
            CreatedAt=now,
            LastUpdatedOn=now,
            Status="active",
            document_count=0,
            documents=[],
        )
        self._write_metadata(metadata)
        return metadata

    def register_document(
        self,
        project_id: str,
        document_id: str,
        filename: str,
        file_size: float,
        pages: int,
    ) -> DocumentMetadata:
        metadata = self.get_project(project_id)
        project_dir = self._project_dir(project_id)
        pdf_path = self.document_pdf_path(project_id, document_id)
        json_path = self.spec_json_path(project_id, document_id)

        document = DocumentMetadata(
            DocumentId=document_id,
            FileName=filename,
            FileSize=file_size,
            Pages=pages,
            UploadDate=self.now(),
            UploadedBy="",
            Status="uploaded",
            DocumentPath=pdf_path.relative_to(project_dir).as_posix(),
            json_path=json_path.relative_to(project_dir).as_posix(),
            tool_id="",
            tool_type="",
            vector_indexed=False,
        )

        documents = [doc for doc in metadata.documents if doc.DocumentId != document_id]
        documents.append(document)
        metadata.documents = sorted(documents, key=lambda doc: doc.UploadDate)
        metadata.document_count = len(metadata.documents)
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return document

    def complete_extraction(
        self,
        project_id: str,
        document_id: str,
        spec: EquipmentSpec,
        vector_indexed: bool,
    ) -> DocumentMetadata:
        metadata = self.get_project(project_id)

        for doc in metadata.documents:
            if doc.DocumentId == document_id:
                doc.Status = "completed"
                doc.tool_id = spec.tool_id
                doc.tool_type = spec.tool_type
                doc.vector_indexed = vector_indexed
                document = doc
                break
        else:
            raise DocumentNotFoundError(
                f"Document '{document_id}' was not found in project '{project_id}'"
            )

        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return document

    def list_projects(self) -> list[ProjectMetadata]:
        projects: list[ProjectMetadata] = []
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            metadata_path = child / self.METADATA_DIR / self.METADATA_FILE
            if not metadata_path.exists():
                logger.warning("Skipping storage folder without metadata: %s", child)
                continue
            projects.append(self._read_metadata(metadata_path))
        return sorted(projects, key=lambda p: p.LastUpdatedOn, reverse=True)

    def get_project(self, project_id: str) -> ProjectMetadata:
        self._validate_id(project_id)
        metadata_path = self._metadata_path(project_id)
        if not metadata_path.exists():
            raise ProjectNotFoundError(f"Project '{project_id}' was not found")
        return self._read_metadata(metadata_path)

    def delete_project(self, project_id: str) -> None:
        self._validate_id(project_id)
        project_dir = self._project_dir(project_id)
        if not self._metadata_path(project_id).exists():
            raise ProjectNotFoundError(f"Project '{project_id}' was not found")
        shutil.rmtree(project_dir)

    def delete_document(self, project_id: str, document_id: str) -> None:
        metadata = self.get_project(project_id)
        document = self.get_document(project_id, document_id)

        pdf_path = self._project_relative_path(project_id, document.DocumentPath)
        json_path = self._project_relative_path(project_id, document.json_path)
        if pdf_path.exists():
            pdf_path.unlink()
        if json_path.exists():
            json_path.unlink()

        metadata.documents = [doc for doc in metadata.documents if doc.DocumentId != document_id]
        metadata.document_count = len(metadata.documents)
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)

    def prepare_document_paths(
        self, project_id: str, original_filename: str
    ) -> tuple[str, Path, Path]:
        metadata = self.get_project(project_id)
        base_id = self.slugify(Path(original_filename).stem, fallback="document")
        existing_ids = {doc.id for doc in metadata.documents}

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
        project_id: str,
        document_id: str,
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
            DocumentId=document_id,
            FileName=original_filename,
            FileSize=file_size,
            Pages=pages,
            UploadDate=self.now(),
            UploadedBy="",
            Status="completed",
            DocumentPath=pdf_path.relative_to(project_dir).as_posix(),
            json_path=json_path.relative_to(project_dir).as_posix(),
            tool_id=spec.tool_id,
            tool_type=spec.tool_type,
            vector_indexed=vector_indexed,
        )

        documents = [doc for doc in metadata.documents if doc.id != document_id]
        documents.append(document)
        metadata.documents = sorted(documents, key=lambda doc: doc.uploaded_at)
        metadata.document_count = len(metadata.documents)
        metadata.LastUpdatedOn = self.now()
        self._write_metadata(metadata)
        return document

    def get_document(self, project_id: str, document_id: str) -> DocumentMetadata:
        metadata = self.get_project(project_id)
        for document in metadata.documents:
            if document.DocumentId == document_id:
                return document
        raise DocumentNotFoundError(
            f"Document '{document_id}' was not found in project '{project_id}'"
        )

    def read_spec_json(self, project_id: str, document_id: str) -> str:
        document = self.get_document(project_id, document_id)
        path = self._project_relative_path(project_id, document.json_path)
        if not path.exists():
            raise DocumentNotFoundError(
                f"Extracted JSON for document '{document_id}' was not found"
            )
        return path.read_text(encoding="utf-8")

    def vectorstore_path(self, project_id: str) -> Path:
        self.get_project(project_id)
        return self._project_dir(project_id) / self.VECTORSTORE_DIR

    def document_pdf_path(self, project_id: str, document_id: str) -> Path:
        self._validate_id(project_id)
        self._validate_id(document_id)
        return self._project_dir(project_id) / self.DOCUMENTS_DIR / f"{document_id}.pdf"

    def spec_json_path(self, project_id: str, document_id: str) -> Path:
        self._validate_id(project_id)
        self._validate_id(document_id)
        return (
            self._project_dir(project_id)
            / self.EXTRACTED_JSON_DIR
            / f"{document_id}.json"
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

    def _ensure_project_dirs(self, project_id: str) -> None:
        self._validate_id(project_id)
        project_dir = self._project_dir(project_id)
        for folder in (
            self.DOCUMENTS_DIR,
            self.EXTRACTED_JSON_DIR,
            self.VECTORSTORE_DIR,
            self.METADATA_DIR,
        ):
            path = project_dir / folder
            self._assert_inside_root(path)
            path.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, project_id: str) -> Path:
        self._validate_id(project_id)
        path = (self.root / project_id).resolve()
        self._assert_inside_root(path)
        return path

    def _metadata_path(self, project_id: str) -> Path:
        return self._project_dir(project_id) / self.METADATA_DIR / self.METADATA_FILE

    def _project_relative_path(self, project_id: str, relative_path: str) -> Path:
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

    def _write_metadata(self, metadata: ProjectMetadata) -> None:
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
