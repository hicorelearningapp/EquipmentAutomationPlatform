from datetime import datetime, timezone

from source.schemas.project import DocumentCategory, DocumentMetadata, ProjectCreate, ToolType
from source.services.document_strategies import (
    DocumentProcessorFactory,
    LogFileProcessingStrategy,
    TextProcessingStrategy,
)
from source.services.sml_template import build_sml_templates
from source.services.storage_service import StorageService


def test_document_category_coerces_log_files():
    document = DocumentMetadata(
        document_id="secs_log",
        document_type="log file",
        filename="secs.log.txt",
        upload_date=datetime.now(timezone.utc),
    )

    assert document.DocumentType == DocumentCategory.LOG_FILES


def test_txt_strategy_uses_category_to_distinguish_logs_from_sml():
    log_strategy = DocumentProcessorFactory.get_strategy(
        "secs.log.txt",
        doc_category=DocumentCategory.LOG_FILES,
    )
    sml_strategy = DocumentProcessorFactory.get_strategy(
        "custom_sml.txt",
        doc_category=DocumentCategory.SML_SCRIPTS,
    )

    assert isinstance(log_strategy, LogFileProcessingStrategy)
    assert isinstance(sml_strategy, TextProcessingStrategy)


def test_list_user_sml_scripts_excludes_system_templates(tmp_path):
    storage = StorageService(storage_root=tmp_path)
    project = storage.create_project(
        ProjectCreate(
            ProjectName="ETCH-Z500",
            VendorName="NanoDyne Systems",
            ProjectCode="ETCH",
            ProjectDescription="Demo",
            Tool=ToolType.ETCH,
        )
    )
    tool_char_dir = storage._project_dir(project.ProjectID) / storage.TOOL_CHAR_DIR
    (tool_char_dir / "general_gem_testing.txt").write_text("system", encoding="utf-8")
    (tool_char_dir / "tool_characterisation_testing.txt").write_text("system", encoding="utf-8")
    (tool_char_dir / "custom_process.txt").write_text("S1F1\n.", encoding="utf-8")
    (tool_char_dir / "notes.md").write_text("not sml", encoding="utf-8")

    assert storage.list_user_sml_scripts(project.ProjectID) == [
        ("custom_process.txt", tool_char_dir / "custom_process.txt")
    ]


def test_build_sml_templates_includes_user_script_by_filename(tmp_path):
    storage = StorageService(storage_root=tmp_path)
    project = storage.create_project(
        ProjectCreate(
            ProjectName="ETCH-Z500",
            VendorName="NanoDyne Systems",
            ProjectCode="ETCH",
            ProjectDescription="Demo",
            Tool=ToolType.ETCH,
        )
    )
    tool_char_dir = storage._project_dir(project.ProjectID) / storage.TOOL_CHAR_DIR
    (tool_char_dir / "operator_check.txt").write_text("S1F1\n.", encoding="utf-8")

    templates = build_sml_templates(project.ProjectID, storage)

    assert "GeneralGEMTesting" in templates
    assert "ToolCharacterisationTesting" in templates
    assert templates["operator_check.txt"][0]["SML"] == "S1F1\n."
