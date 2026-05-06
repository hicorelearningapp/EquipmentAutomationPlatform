import json
import logging
import re
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

    def create_project(self, name: str) -> ProjectMetadata:
        display_name = name.strip()
        if not display_name:
            raise InvalidSlugError("Project name cannot be empty")

        slug = self.slugify(display_name, fallback="project")
        project_dir = self._project_dir(slug)
        metadata_path = self._metadata_path(slug)

        if metadata_path.exists():
            raise ProjectExistsError(f"A project named '{name}' already exists as '{slug}'")
        if project_dir.exists() and any(project_dir.iterdir()):
            raise ProjectExistsError(
                f"Project folder '{project_dir}' already exists but has no metadata file"
            )

        self._ensure_project_dirs(slug)
        now = self.now()
        metadata = ProjectMetadata(
            name=display_name,
            slug=slug,
            created_at=now,
            updated_at=now,
            document_count=0,
            documents=[],
        )
        self._write_metadata(metadata)
        return metadata

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
        return sorted(projects, key=lambda p: p.updated_at, reverse=True)

    def get_project(self, slug: str) -> ProjectMetadata:
        self._validate_slug(slug)
        metadata_path = self._metadata_path(slug)
        if not metadata_path.exists():
            raise ProjectNotFoundError(f"Project '{slug}' was not found")
        return self._read_metadata(metadata_path)

    def prepare_document_paths(
        self, project_slug: str, original_filename: str
    ) -> tuple[str, Path, Path]:
        metadata = self.get_project(project_slug)
        base_id = self.slugify(Path(original_filename).stem, fallback="document")
        existing_ids = {doc.id for doc in metadata.documents}

        document_id = base_id
        counter = 2
        while (
            document_id in existing_ids
            or self.document_pdf_path(project_slug, document_id).exists()
            or self.spec_json_path(project_slug, document_id).exists()
        ):
            document_id = f"{base_id}_{counter}"
            counter += 1

        return (
            document_id,
            self.document_pdf_path(project_slug, document_id),
            self.spec_json_path(project_slug, document_id),
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
        project_slug: str,
        document_id: str,
        original_filename: str,
        spec: EquipmentSpec,
        vector_indexed: bool,
    ) -> DocumentMetadata:
        metadata = self.get_project(project_slug)
        project_dir = self._project_dir(project_slug)
        pdf_path = self.document_pdf_path(project_slug, document_id)
        json_path = self.spec_json_path(project_slug, document_id)

        document = DocumentMetadata(
            id=document_id,
            original_filename=original_filename,
            pdf_path=pdf_path.relative_to(project_dir).as_posix(),
            json_path=json_path.relative_to(project_dir).as_posix(),
            tool_id=spec.tool_id,
            tool_type=spec.tool_type,
            uploaded_at=self.now(),
            extraction_status="completed",
            vector_indexed=vector_indexed,
        )

        documents = [doc for doc in metadata.documents if doc.id != document_id]
        documents.append(document)
        metadata.documents = sorted(documents, key=lambda doc: doc.uploaded_at)
        metadata.document_count = len(metadata.documents)
        metadata.updated_at = self.now()
        self._write_metadata(metadata)
        return document

    def get_document(self, project_slug: str, document_id: str) -> DocumentMetadata:
        metadata = self.get_project(project_slug)
        for document in metadata.documents:
            if document.id == document_id:
                return document
        raise DocumentNotFoundError(
            f"Document '{document_id}' was not found in project '{project_slug}'"
        )

    def read_spec_json(self, project_slug: str, document_id: str) -> str:
        document = self.get_document(project_slug, document_id)
        path = self._project_relative_path(project_slug, document.json_path)
        if not path.exists():
            raise DocumentNotFoundError(
                f"Extracted JSON for document '{document_id}' was not found"
            )
        return path.read_text(encoding="utf-8")

    def vectorstore_path(self, project_slug: str) -> Path:
        self.get_project(project_slug)
        return self._project_dir(project_slug) / self.VECTORSTORE_DIR

    def document_pdf_path(self, project_slug: str, document_id: str) -> Path:
        self._validate_slug(project_slug)
        self._validate_slug(document_id)
        return self._project_dir(project_slug) / self.DOCUMENTS_DIR / f"{document_id}.pdf"

    def spec_json_path(self, project_slug: str, document_id: str) -> Path:
        self._validate_slug(project_slug)
        self._validate_slug(document_id)
        return (
            self._project_dir(project_slug)
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

    def _ensure_project_dirs(self, slug: str) -> None:
        self._validate_slug(slug)
        project_dir = self._project_dir(slug)
        for folder in (
            self.DOCUMENTS_DIR,
            self.EXTRACTED_JSON_DIR,
            self.VECTORSTORE_DIR,
            self.METADATA_DIR,
        ):
            path = project_dir / folder
            self._assert_inside_root(path)
            path.mkdir(parents=True, exist_ok=True)

    def _project_dir(self, slug: str) -> Path:
        self._validate_slug(slug)
        path = (self.root / slug).resolve()
        self._assert_inside_root(path)
        return path

    def _metadata_path(self, slug: str) -> Path:
        return self._project_dir(slug) / self.METADATA_DIR / self.METADATA_FILE

    def _project_relative_path(self, project_slug: str, relative_path: str) -> Path:
        if Path(relative_path).is_absolute():
            raise InvalidSlugError("Stored project paths must be relative")
        project_dir = self._project_dir(project_slug)
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
        self._ensure_project_dirs(metadata.slug)
        path = self._metadata_path(metadata.slug)
        payload = json.dumps(metadata.model_dump(mode="json"), indent=2)
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(payload + "\n", encoding="utf-8")
        temp_path.replace(path)

    def _validate_slug(self, slug: str) -> None:
        if slug != self.slugify(slug):
            raise InvalidSlugError(f"Invalid slug: {slug}")

    def _assert_inside_root(self, path: Path) -> None:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise InvalidSlugError(f"Path escapes EAP_STORAGE_ROOT: {path}")
