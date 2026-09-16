"""SML script templates loaded from the scripts folder.

Source: "Tool Characterization Testing Sequence Template.docx"
"""
import json
import logging
from pathlib import Path

from source.services.test_script_service import TestScriptService

logger = logging.getLogger(__name__)

from source.app_paths import gem_templates_dir

SCRIPTS_DIR = gem_templates_dir()

SML_TEMPLATE_FILENAME = "ToolCharacterizationTestScriptjson (1).txt"


def _load_json_template(filename: str) -> list:
    path = SCRIPTS_DIR / filename
    if path.exists():
        content = path.read_text(encoding="utf-8")
        try:
            return json.loads(content)
        except Exception:
            return []
    return []


SML_GENERAL_TEMPLATE = _load_json_template("GeneraltestScriptjson (1).txt")
SML_CHARACTERISATION_TEMPLATE = _load_json_template("ToolCharacterizationTestScriptjson (1).txt")

SML_TEMPLATES = {
    "GeneralGEMTesting": SML_GENERAL_TEMPLATE,
    "ToolCharacterisationTesting": SML_CHARACTERISATION_TEMPLATE,
}

# For backward compatibility with storage_service or other legacy code
SML_TEMPLATE_CONTENT = SML_CHARACTERISATION_TEMPLATE

_test_script_service = TestScriptService()


def _tests_to_sml_string(tests: list) -> str:
    raw_sml_blocks = []
    for test in tests:
        sml = test.get("SML", "").strip()
        if sml:
            raw_sml_blocks.append(sml)
    return "\n\n".join(raw_sml_blocks)


def build_sml_templates(project_id: int, storage) -> dict:
    """
    Build the project SmlTemplate response with system templates and user SML scripts.
    """
    result = {
        "GeneralGEMTesting": _tests_to_sml_string(SML_GENERAL_TEMPLATE),
        "ToolCharacterisationTesting": _tests_to_sml_string(SML_CHARACTERISATION_TEMPLATE),
    }
    try:
        user_scripts = storage.list_user_sml_scripts(project_id)
        for filename, path in user_scripts:
            try:
                content = path.read_text(encoding="utf-8")
                # Strip the extension for the UI key
                key = Path(filename).stem
                
                # If it's valid JSON list, reconstruct SML. Otherwise, it's raw SML text.
                try:
                    import json
                    tests = json.loads(content)
                    if isinstance(tests, list):
                        result[key] = _tests_to_sml_string(tests)
                    else:
                        result[key] = content
                except Exception:
                    result[key] = content
                    
            except Exception as e:
                logger.warning("Failed to parse user SML script %s: %s", filename, e)
    except Exception as e:
        logger.warning("Failed to list user SML scripts for project %s: %s", project_id, e)
    return result
