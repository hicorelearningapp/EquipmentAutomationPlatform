"""SML script templates loaded from the scripts folder.

Source: "Tool Characterization Testing Sequence Template.docx"
"""
import json
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent.parent / "GEMTestScriptTemplates"

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
