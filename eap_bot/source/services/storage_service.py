import json
import logging
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from source.config import settings
from source.schemas.project import DocumentMetadata, ProjectMetadata, ProjectCreate, ProjectOut, TestResultFileType
from source.schemas.mapping import ProjectMapping
from source.schemas.secsgem import EquipmentSpec
from source.services.sml_template import SML_CHARACTERISATION_TEMPLATE, SML_TEMPLATE_FILENAME

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


class DocumentExistsError(StorageError):
    pass


class StorageService:
    DOCUMENTS_DIR = "Documents"
    MESTAG_DIR = "MESTemplates"
    EXTRACTED_JSON_DIR = "ExtractedJson"
    VECTORSTORE_DIR = "Vectorstore"
    EXTRACTED_TABLES_DIR = "ExtractedTables"
    METADATA_DIR = "ProjectsMetadata"
    CODE_DIR = "Code"
    TOOL_CHAR_DIR = "ToolCharacterization"
    TEST_SUMMARY_DIR = "TestSummary"
    SMART_AUTO_CODE_DIR = "SmartAutoCode"
    MES_MAPPING_JSON_DIR = "MESMappingJSON"
    REPORTS_DIR = "Reports"
    RESULTS_DIR = "Results"
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
        existing_projects = self.list_projects()
        for p in existing_projects:
            if p.ProjectName.lower() == project_create.ProjectName.lower():
                raise ProjectExistsError(f"Project with name '{project_create.ProjectName}' already exists.")
                
        project_id = self._get_next_id()
        self._ensure_project_dirs(project_id)
        
        now = self.now()
        metadata = ProjectOut(
            ProjectID=project_id,
            ProjectName=project_create.ProjectName,
            ProjectVersion="1.0",
            VendorName=project_create.VendorName,
            ProjectCode=project_create.ProjectCode,
            ProjectDescription=project_create.ProjectDescription,
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
        self.write_sml_template(project_id)
        return document

    def sml_template_path(self, project_id: int) -> Path:
        return self._project_dir(project_id) / SML_TEMPLATE_FILENAME

    def write_sml_template(self, project_id: int) -> None:
        """Drop the hardcoded SML script template into the project directory.

        Idempotent: only writes if the file does not already exist, so re-running
        Analyze on the same project does not clobber edits made downstream.
        """
        path = self.sml_template_path(project_id)
        if path.exists():
            return
        path.write_text(json.dumps(SML_CHARACTERISATION_TEMPLATE, indent=2), encoding="utf-8")
        logger.info("Wrote SML template to %s", path)

    def save_mes_mapping(self, project_id: int, family: str, template: str, data: dict) -> Path:
        self.get_project(project_id)
        # Handle template names that might have .json extension
        template_name = template if template.lower().endswith(".json") else f"{template}.json"
        template_name = template_name.replace(".json", "_mapped.json")
        
        mapping_dir = self._project_dir(project_id) / self.MES_MAPPING_JSON_DIR / family
        mapping_dir.mkdir(parents=True, exist_ok=True)
        
        mapping_path = mapping_dir / template_name
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
        logger.info(f"Saved MES Mapping to {mapping_path}")
        return mapping_path

    def save_multiple_test_results(self, project_id: int, tool_id: str, files_data: list[dict], file_type: str = "unknown") -> list[str]:
        self.get_project(project_id)
        
        timestamp = self.now().strftime("%Y-%m-%d_%H-%M-%S")
        saved_paths = []
        
        results_dir = self._project_dir(project_id) / self.RESULTS_DIR / tool_id / timestamp
        results_dir.mkdir(parents=True, exist_ok=True)
        
        for data in files_data:
            file_name = data["file_name"]
            file_bytes = data["file_bytes"]
            test_script_names = data["test_script_names"]
            file_type_to_save = data.get("file_type", file_type)
            
            # Save metadata so we can identify this file's type later
            file_stem = Path(file_name).stem
            meta_path = results_dir / f"{file_stem}_metadata.json"
            meta_data = {
                "file_name": file_name,
                "file_type": file_type_to_save,
                "test_script_names": test_script_names
            }
            meta_path.write_text(json.dumps(meta_data, indent=2), encoding="utf-8")
            
            file_path = results_dir / file_name
            file_path.write_bytes(file_bytes)
            saved_paths.append(str(file_path))
            
        return saved_paths

    def get_all_tool_results(self, project_id: int, tool_id: str) -> dict:
        self.get_project(project_id)
        
        results_dir = self._project_dir(project_id) / self.RESULTS_DIR / tool_id
        
        executions = []
        
        if results_dir.exists():
            for ts_dir in sorted(results_dir.iterdir(), key=lambda d: d.name, reverse=True):
                if not ts_dir.is_dir():
                    continue
                
                timestamp = ts_dir.name
                
                # Dictionary to group by script_name: { "script_name": {"test": item, "secs_log": item} }
                scripts_map = {}
                
                # Check for metadata files in ts_dir (new structure)
                for meta_file in ts_dir.glob("*_metadata.json"):
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        file_name = meta.get("file_name")
                        file_type = meta.get("file_type")
                        test_script_names = meta.get("test_script_names", [])
                        
                        if not file_name:
                            continue
                        
                        file_path = ts_dir / file_name
                        if not file_path.exists():
                            continue
                            
                        # Normalize file type
                        lower_type = str(file_type).lower()
                        if lower_type in ("test", "report", "summary_json"):
                            norm_type = "Test"
                            key_type = "test"
                        elif lower_type in ("secslog", "secs_log", "secs"):
                            norm_type = "SECSLog"
                            key_type = "secs_log"
                        else:
                            norm_type = file_type
                            key_type = file_type.lower()

                        item_path = f"/projects/{project_id}/Results/{tool_id}/{timestamp}/{file_name}"

                        item = {
                            "file_name": file_name,
                            "file_type": norm_type,
                            "path": item_path
                        }
                        
                        for script_name in test_script_names:
                            if script_name.isdigit():
                                continue
                            if script_name not in scripts_map:
                                scripts_map[script_name] = {}
                            scripts_map[script_name][key_type] = item
                    except Exception as e:
                        logger.error(f"Error parsing metadata file {meta_file}: {e}")

                # Check for metadata files in subdirectories (old structure)
                for script_dir in ts_dir.iterdir():
                    if not script_dir.is_dir():
                        continue
                    
                    old_meta_file = script_dir / "metadata.json"
                    if old_meta_file.exists():
                        try:
                            meta = json.loads(old_meta_file.read_text(encoding="utf-8"))
                            file_type = meta.get("file_type")
                            
                            # Find the actual file (non-metadata) in that directory
                            for f in script_dir.iterdir():
                                if f.is_file() and f.name != "metadata.json":
                                    file_name = f.name
                                    file_path = f
                                    
                                    lower_type = str(file_type).lower()
                                    if lower_type in ("test", "report", "summary_json"):
                                        norm_type = "Test"
                                        key_type = "test"
                                    elif lower_type in ("secslog", "secs_log", "secs"):
                                        norm_type = "SECSLog"
                                        key_type = "secs_log"
                                    else:
                                        norm_type = file_type
                                        key_type = file_type.lower()

                                    script_name = script_dir.name
                                    item_path = f"/projects/{project_id}/Results/{tool_id}/{timestamp}/{script_name}/{file_name}"

                                    item = {
                                        "file_name": file_name,
                                        "file_type": norm_type,
                                        "path": item_path
                                    }
                                    
                                    if script_name not in scripts_map:
                                        scripts_map[script_name] = {}
                                    scripts_map[script_name][key_type] = item
                                    break
                        except Exception as e:
                            logger.error(f"Error parsing old metadata file {old_meta_file}: {e}")

                if scripts_map:
                    scripts_list = []
                    for script_name, artifacts in sorted(scripts_map.items()):
                        scripts_list.append({
                            "script_name": script_name,
                            "artifacts": artifacts
                        })
                    
                    executions.append({
                        "execution_time": timestamp,
                        "script_count": len(scripts_list),
                        "scripts": scripts_list
                    })

        return {
            "status": "success",
            "tool_id": tool_id,
            "execution_count": len(executions),
            "executions": executions
        }

    def get_latest_test_summary(self, project_id: int, tool_id: Optional[str] = None) -> Any:
        self.get_project(project_id)
        
        project_dir = self._project_dir(project_id)
        results_dir = project_dir / self.RESULTS_DIR
        if not results_dir.exists():
            return None

        def find_summary_in_ts_dir(ts_dir: Path) -> Optional[Path]:
            # Old structure: ts_dir / "summary.json"
            if (ts_dir / "summary.json").exists():
                return ts_dir / "summary.json"
                
            # Current structure: metadata file tells us the file type
            for f in ts_dir.glob("*_metadata.json"):
                try:
                    meta = json.loads(f.read_text(encoding="utf-8"))
                    if meta.get("file_type") == "summary_json":
                        report_file = ts_dir / meta.get("file_name", "")
                        if report_file.exists():
                            return report_file
                except Exception:
                    pass
                    
            # Fallback for previous structure: ts_dir / {test_script_name} / {original_name.json}
            for script_dir in ts_dir.iterdir():
                if script_dir.is_dir():
                    for f in script_dir.iterdir():
                        if f.is_file() and f.name.endswith(".json") and "summary" in f.name.lower():
                            return f
            return None
            
        if tool_id:
            tool_dir = results_dir / tool_id
            if not tool_dir.exists():
                return None
            timestamps = sorted([d.name for d in tool_dir.iterdir() if d.is_dir()])
            for ts in reversed(timestamps):
                summary_file = find_summary_in_ts_dir(tool_dir / ts)
                if summary_file:
                    return json.loads(summary_file.read_text(encoding="utf-8"))
            return None
        else:
            all_summaries = []
            for t_dir in results_dir.iterdir():
                if t_dir.is_dir():
                    timestamps = sorted([d.name for d in t_dir.iterdir() if d.is_dir()])
                    for ts in reversed(timestamps):
                        summary_file = find_summary_in_ts_dir(t_dir / ts)
                        if summary_file:
                            all_summaries.append((ts, summary_file))
                            break
            if not all_summaries:
                return None
            all_summaries.sort(key=lambda x: x[0])
            latest_summary_file = all_summaries[-1][1]
            return json.loads(latest_summary_file.read_text(encoding="utf-8"))

    def get_test_reports(self, project_id: int, tool_id: str, script_names: list[str]) -> dict[str, Any]:
        self.get_project(project_id)
        
        results_dir = self._project_dir(project_id) / self.RESULTS_DIR / tool_id
        if not results_dir.exists():
            return {}
            
        # Iterate over all script names the user requested
        reports = {}
        for target_script in script_names:
            # Sort timestamps newest to oldest
            timestamps = sorted([d.name for d in results_dir.iterdir() if d.is_dir()], reverse=True)
            for ts in timestamps:
                ts_dir = results_dir / ts
                
                # Check current structure: metadata files in ts_dir
                found_report = False
                for meta_file in ts_dir.glob("*_metadata.json"):
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        if meta.get("file_type") == "report" and target_script in meta.get("test_script_names", []):
                            report_file = ts_dir / meta.get("file_name", "")
                            if report_file.exists():
                                reports[target_script] = json.loads(report_file.read_text(encoding="utf-8"))
                                found_report = True
                                break
                    except Exception as e:
                        logger.error("Failed to parse metadata or report for %s: %s", target_script, e)
                        
                if found_report:
                    break  # Stop looking at older timestamps for this script
                    
                # Fallback for previous structure: subfolders with script name
                matching_dirs = [d for d in ts_dir.iterdir() if d.is_dir() and target_script.lower() in d.name.lower()]
                if not matching_dirs:
                    continue
                    
                # We found a matching folder. Check if it has a report metadata
                script_dir = matching_dirs[0]
                meta_file = script_dir / "metadata.json"
                if meta_file.exists():
                    try:
                        meta = json.loads(meta_file.read_text(encoding="utf-8"))
                        if meta.get("file_type") == "report":
                            # It is a report. Find the actual json file that is not metadata.json
                            for f in script_dir.iterdir():
                                if f.is_file() and f.name.endswith(".json") and f.name != "metadata.json":
                                    reports[target_script] = json.loads(f.read_text(encoding="utf-8"))
                                    found_report = True
                                    break
                            if found_report:
                                break
                    except Exception as e:
                        logger.error("Failed to parse fallback metadata or report for %s: %s", target_script, e)
                        
        return reports

    def count_connected_equipments(self, project_id: int) -> int:
        """Count tool subdirectories under Results/ as connected equipments."""
        results_dir = self._project_dir(project_id) / self.RESULTS_DIR
        if not results_dir.exists():
            return 0
        return len([d for d in results_dir.iterdir() if d.is_dir()])

    def vectorstore_path_for_category(self, project_id: int, category_slug: str) -> Path:
        """
        Return the FAISS directory for a specific document category or 'tables'.
        """
        self.get_project(project_id)
        return self._project_dir(project_id) / self.VECTORSTORE_DIR / category_slug

    def all_vectorstore_paths(self, project_id: int) -> dict[str, Path]:
        """
        Return a dict mapping category_slug -> Path for every known
        FAISS subdirectory under this project's Vectorstore/ folder.
        """
        self.get_project(project_id)
        base = self._project_dir(project_id) / self.VECTORSTORE_DIR
        all_slugs = [
            "gem_manual",
            "user_manuals",
            "troubleshooting_guidance",
            "variable_files",
            "log_files",
            "sml_scripts",
            "tables",
        ]
        result = {
            slug: base / slug
            for slug in all_slugs
            if (base / slug).exists() and any((base / slug).iterdir())
        }
        # Legacy compatibility: if the project has a flat (pre-category) vectorstore, include it
        legacy_path = base
        if legacy_path.exists() and (legacy_path / "index.faiss").exists():
            result["legacy"] = legacy_path
        return result

    def list_user_sml_scripts(self, project_id: int) -> list[tuple[str, Path]]:
        """
        Return user SML .txt files in ToolCharacterization, excluding protected templates.
        """
        system_templates = {"general_gem_testing.txt", "tool_characterisation_testing.txt"}
        tool_char_dir = self._project_dir(project_id) / self.TOOL_CHAR_DIR
        if not tool_char_dir.exists():
            return []
        return [
            (f.name, f)
            for f in sorted(tool_char_dir.iterdir())
            if f.is_file() and f.suffix == ".txt" and f.name not in system_templates
        ]

    @staticmethod
    def _doc_category_to_slug(document_category) -> str:
        """
        Convert a DocumentCategory enum instance or its string value
        to the filesystem slug used as the FAISS subdirectory name.
        """
        val = document_category.value if hasattr(document_category, "value") else str(document_category)
        return val.strip().lower().replace(" ", "_").replace("/", "_")

    def get_populated_categories(self, project_id: int) -> list[str]:
        """
        Return the human-readable DocumentCategory values for which
        a non-empty FAISS vectorstore exists for this project.
        The internal 'tables' store is treated as 'Variable Files'.
        """
        from source.schemas.project import DocumentCategory
        self.get_project(project_id)
        base = self._project_dir(project_id) / self.VECTORSTORE_DIR

        slug_to_label = {
            self._doc_category_to_slug(cat): cat.value
            for cat in DocumentCategory
        }

        populated = set()
        for slug, label in slug_to_label.items():
            store_path = base / slug
            if store_path.exists() and any(store_path.iterdir()):
                populated.add(label)

        # If the internal 'tables' store is non-empty, also expose 'Variable Files'
        tables_path = base / "tables"
        if tables_path.exists() and any(tables_path.iterdir()):
            populated.add(DocumentCategory.VARIABLE_FILES.value)

        # Return in stable enum definition order
        return [cat.value for cat in DocumentCategory if cat.value in populated]

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
        
        if update.ProjectName is not None and update.ProjectName != metadata.ProjectName:
            existing_projects = self.list_projects()
            for p in existing_projects:
                if p.ProjectID != project_id and p.ProjectName.lower() == update.ProjectName.lower():
                    raise ProjectExistsError(f"Project with name '{update.ProjectName}' already exists.")
            metadata.ProjectName = update.ProjectName
        if update.VendorName is not None:
            metadata.VendorName = update.VendorName
        if getattr(update, "ProjectCode", None) is not None:
            metadata.ProjectCode = update.ProjectCode
        if getattr(update, "ProjectDescription", None) is not None:
            metadata.ProjectDescription = update.ProjectDescription
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

        pdf_path = self.document_pdf_path(project_id, document_id)
        json_path = self.spec_json_path(project_id, document_id)
        if pdf_path.exists():
            pdf_path.unlink()
        if json_path.exists():
            json_path.unlink()

        metadata.Documents = [doc for doc in metadata.Documents if doc.DocumentID != document_id]
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
        self, project_id: int, original_filename: str, extension: str = ".pdf", doc_category: Optional[Any] = None
    ) -> tuple[str, Path, Path]:
        metadata = self.get_project(project_id)
        
        is_sml = doc_category and (str(doc_category) == "SML Scripts" or getattr(doc_category, "value", "") == "SML Scripts")
        
        if not is_sml:
            for doc in metadata.Documents:
                if doc.FileName.lower() == original_filename.lower():
                    raise DocumentExistsError(
                        f"Document '{original_filename}' already exists in project '{project_id}'."
                    )

        base_id = self.slugify(Path(original_filename).stem, fallback="document")
        existing_ids = {doc.DocumentID for doc in metadata.Documents}
        docs_dir = self._project_dir(project_id) / self.DOCUMENTS_DIR

        document_id = base_id
        counter = 2
        
        def is_id_taken(did: str) -> bool:
            if is_sml:
                existing_doc = next((d for d in metadata.Documents if d.DocumentID == did), None)
                if existing_doc and existing_doc.FileName.lower() == original_filename.lower():
                    return False
                    
            if did in existing_ids:
                return True
            if self.spec_json_path(project_id, did).exists():
                return True
            if (docs_dir / f"{did}{extension}").exists():
                return True
            nested_dir = docs_dir / did
            if nested_dir.exists() and any(nested_dir.iterdir()):
                return True
            return False

        while is_id_taken(document_id):
            document_id = f"{base_id}_{counter}"
            counter += 1

        if is_sml:
            timestamp = self.now().strftime("%Y-%m-%d_%H-%M-%S")
            file_path = docs_dir / document_id / timestamp / original_filename
        else:
            file_path = docs_dir / f"{document_id}{extension}"

        return (
            document_id,
            file_path,
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
            from source.schemas.mapping import ProjectMapping
            return ProjectMapping(ProjectID=project_id)
        try:
            from source.schemas.mapping import ProjectMapping
            return ProjectMapping.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            from source.schemas.mapping import ProjectMapping
            return ProjectMapping(ProjectID=project_id)

    def save_mapping(self, project_id: int, mapping: ProjectMapping) -> None:
        path = self.mapping_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(mapping.model_dump_json(indent=2), encoding="utf-8")

    def save_automap_result(self, project_id: int, family: str, template: str, result: dict) -> None:
        """Save the full template with AutoMapping to MESMappingJSON/{family}/{template}"""
        self.get_project(project_id)
        path = self._project_dir(project_id) / self.MES_MAPPING_JSON_DIR / family / template
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        logger.info("Saved AutoMap result for project %s to %s", project_id, path)

    def load_automap_result(self, project_id: int, family: str, template: str) -> dict | None:
        """Load previously saved AutoMap result, or None if not found."""
        path = self._project_dir(project_id) / self.MES_MAPPING_JSON_DIR / family / template
        if path.exists():
            import json
            return json.loads(path.read_text(encoding="utf-8"))
        return None

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

    def extracted_tables_path(self, project_id: int) -> Path:
        return self._project_dir(project_id) / self.EXTRACTED_TABLES_DIR

    def save_extracted_tables(self, project_id: int, spec: "EquipmentSpec") -> None:
        import csv
        from pydantic import BaseModel

        def _cell_to_str(val: Any) -> str:
            if val is None:
                return ""
            if isinstance(val, BaseModel):
                return json.dumps(val.model_dump(), ensure_ascii=False)
            if isinstance(val, list):
                return json.dumps(
                    [v.model_dump() if isinstance(v, BaseModel) else v for v in val],
                    ensure_ascii=False,
                )
            return str(val)

        tables_dir = self.extracted_tables_path(project_id)
        tables_dir.mkdir(parents=True, exist_ok=True)

        table_configs = [
            (
                "status_variables.csv",
                ["SVID", "Name", "Description", "DataType", "AccessType", "Value", "Confidence"],
                spec.StatusVariables,
                "SVID",
            ),
            (
                "data_variables.csv",
                ["DvID", "Name", "ValueType", "Unit"],
                spec.DataVariables,
                "DvID",
            ),
            (
                "events.csv",
                ["CEID", "Name", "Description", "LinkedVIDs", "LinkedReports", "Confidence"],
                spec.Events,
                "CEID",
            ),
            (
                "alarms.csv",
                ["AlarmID", "Name", "Severity", "LinkedVID", "Description", "Confidence"],
                spec.Alarms,
                "AlarmID",
            ),
            (
                "remote_commands.csv",
                ["RCMD", "Description", "Parameters", "Confidence"],
                spec.RemoteCommands,
                "RCMD",
            ),
            (
                "states.csv",
                ["StateID", "Name", "Description"],
                spec.States,
                "StateID",
            ),
            (
                "state_transitions.csv",
                ["FromState", "ToState", "TriggerEvent", "TriggerCommand", "Manual"],
                spec.StateTransitions,
                None,  # dedup by (FromState, ToState) tuple
            ),
        ]

        for filename, headers, items, id_field in table_configs:
            csv_path = tables_dir / filename
            existing: dict = {}

            # Load existing rows keyed by primary ID
            if csv_path.exists():
                with open(csv_path, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames and (not id_field or id_field in reader.fieldnames):
                        for row in reader:
                            if id_field:
                                if row.get(id_field):
                                    existing[row[id_field]] = row
                            else:
                                if "FromState" in row and "ToState" in row:
                                    key = (row["FromState"], row["ToState"])
                                    existing[key] = row
                    else:
                        logger.warning("Existing CSV %s has mismatched or missing headers. Skipping existing rows.", filename)

            # Merge new items — new data wins on conflict
            for item in items:
                row = {h: _cell_to_str(getattr(item, h, None)) for h in headers}
                if id_field:
                    key = row[id_field]
                else:
                    key = (row["FromState"], row["ToState"])
                existing[key] = row

            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(existing.values())

            logger.info("Saved %d rows to %s", len(existing), csv_path)


    def mapping_path(self, project_id: int) -> Path:
        return self._project_dir(project_id) / self.MES_MAPPING_JSON_DIR / "mes_mapping.json"

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

    def _find_nested_document(self, docs_dir: Path, document_id: str) -> Optional[Path]:
        nested_dir = docs_dir / document_id
        if nested_dir.exists() and nested_dir.is_dir():
            for ts_dir in sorted(nested_dir.iterdir(), key=lambda x: x.name, reverse=True):
                if ts_dir.is_dir():
                    for f in ts_dir.iterdir():
                        if f.is_file():
                            return f
        return None

    def document_pdf_path(self, project_id: int, document_id: str) -> Path:
        docs_dir = self._project_dir(project_id) / self.DOCUMENTS_DIR
        nested_file = self._find_nested_document(docs_dir, document_id)
        if nested_file:
            return nested_file
        return docs_dir / f"{document_id}.pdf"

    def document_excel_path(self, project_id: int, document_id: str, ext: str = ".xlsx") -> Path:
        docs_dir = self._project_dir(project_id) / self.DOCUMENTS_DIR
        nested_file = self._find_nested_document(docs_dir, document_id)
        if nested_file:
            return nested_file
        return docs_dir / f"{document_id}{ext}"

    def spec_json_path(self, project_id: int, document_id: str) -> Path:
        return (
            self._project_dir(project_id)
            / self.EXTRACTED_JSON_DIR
            / f"{document_id}.json"
        )

    def questions_json_path(self, project_id: int) -> Path:
        return self._project_dir(project_id) / "Questions" / "questions.json"

    def get_questions(self, project_id: int) -> list[dict[str, str]]:
        path = self.questions_json_path(project_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                # Legacy format: dict mapping filename to list of QA dicts
                flat_list = []
                for qa_list in data.values():
                    if isinstance(qa_list, list):
                        flat_list.extend(qa_list)
                return flat_list
            elif isinstance(data, list):
                return data
            return []
        except Exception as exc:
            logger.error("Failed to read questions JSON: %s", exc)
            return []

    def save_questions(self, project_id: int, questions_data: list[dict[str, str]]) -> None:
        path = self.questions_json_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(questions_data, indent=2), encoding="utf-8")

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
            self.EXTRACTED_TABLES_DIR,
            self.TOOL_CHAR_DIR,
            self.TEST_SUMMARY_DIR,
            self.SMART_AUTO_CODE_DIR,
            self.MES_MAPPING_JSON_DIR,
            self.REPORTS_DIR,
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
        except Exception as exc:
            import traceback
            raise StorageError(f"Could not read project metadata at {path}. Exception: {exc}\nTraceback: {traceback.format_exc()}") from exc

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
