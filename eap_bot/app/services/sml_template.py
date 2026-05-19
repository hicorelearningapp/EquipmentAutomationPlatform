"""SML script templates loaded from the scripts folder.

Source: "Tool Characterization Testing Sequence Template.docx"
"""
from pathlib import Path

SML_TEMPLATE_FILENAME = "tool_characterization_sequence.txt"

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _load_template(filename: str) -> str:
    path = SCRIPTS_DIR / filename
    if path.exists():
        content = path.read_text(encoding="utf-8")
        # Ensure it has leading/trailing newlines to match the legacy triple-quoted string shape
        if not content.startswith("\n"):
            content = "\n" + content
        if not content.endswith("\n"):
            content = content + "\n"
        return content
    return ""


SML_GENERAL_TEMPLATE = _load_template("general_gem_testing.txt")
SML_CHARACTERISATION_TEMPLATE = _load_template("tool_characterisation_testing.txt")

SML_TEMPLATES = {
    "GeneralGEMTesting": SML_GENERAL_TEMPLATE,
    "ToolCharacterisationTesting": SML_CHARACTERISATION_TEMPLATE,
}

# For backward compatibility with storage_service or other legacy code
SML_TEMPLATE_CONTENT = SML_CHARACTERISATION_TEMPLATE
