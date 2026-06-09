# eap_bot Implementation Plan

## Overview

Four self-contained work items. Each section states exactly what to change, in which file, and why. No ambiguity. Do not change anything outside the files listed in each section.

---

## Work Item 1 — SML File Upload: System Templates Are Never Overwritten

### Problem

`project_service.py → aggregate_project_data()` copies the two system template files (`general_gem_testing.txt`, `tool_characterisation_testing.txt`) from `GEMTestScriptTemplates/` into `ToolCharacterization/` **unconditionally** whenever `has_user_sml` is `False`. This means:

- If a user deletes their uploaded SML document (removing it from metadata), the next call to `aggregate_project_data()` sees `has_user_sml = False` and **overwrites** whatever is currently in `ToolCharacterization/` — even files the user has manually edited.
- If a user uploads a file named exactly `tool_characterisation_testing.txt`, `TextProcessingStrategy.post_upload` writes it to `ToolCharacterization/tool_characterisation_testing.txt`, then any subsequent `aggregate_project_data()` call with `has_user_sml = False` immediately overwrites it with the factory template.

### Rule Going Forward

The two system template files **must never be overwritten by any code path**. They are seeded once and protected forever.

### Changes

#### File: `source/services/project_service.py`

Inside `aggregate_project_data()`, find the block:

```python
if not has_user_sml:
    try:
        from source.services.sml_template import SCRIPTS_DIR
        tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
        tool_char_dir.mkdir(parents=True, exist_ok=True)
        for script_name in ["general_gem_testing.txt", "tool_characterisation_testing.txt"]:
            src_path = SCRIPTS_DIR / script_name
            if src_path.exists():
                content = src_path.read_text(encoding="utf-8")
                dst_path = tool_char_dir / script_name
                dst_path.write_text(content, encoding="utf-8")
                logger.info("Saved script %s to %s", script_name, dst_path)
    except Exception as e:
        logger.error("Failed to copy script templates for project %s: %s", project_id, e)
else:
    logger.info("Project %s has user-uploaded SML scripts; skipping template copy", project_id)
```

**Replace it with:**

```python
# Always seed system templates if they don't already exist on disk.
# Never overwrite them regardless of has_user_sml — they are protected forever.
try:
    from source.services.sml_template import SCRIPTS_DIR
    tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
    tool_char_dir.mkdir(parents=True, exist_ok=True)
    for script_name in ["general_gem_testing.txt", "tool_characterisation_testing.txt"]:
        dst_path = tool_char_dir / script_name
        if dst_path.exists():
            logger.debug("System template %s already exists, skipping", script_name)
            continue
        src_path = SCRIPTS_DIR / script_name
        if src_path.exists():
            dst_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("Seeded system template %s to %s", script_name, dst_path)
except Exception as e:
    logger.error("Failed to seed script templates for project %s: %s", project_id, e)
```

**Explanation of the change:** Removed the `has_user_sml` branch entirely. The seed now always runs but is gated by `if dst_path.exists(): continue`, meaning it writes only once (on first creation) and never again.

---

## Work Item 2 — SML Template Section: Include User-Uploaded Scripts Alongside System Templates

### Current Behaviour

`sml_template.py` loads `SML_TEMPLATES` as a module-level constant with two fixed keys: `GeneralGEMTesting` and `ToolCharacterisationTesting`. This dict is returned verbatim in every response. User-uploaded `.txt` files are never included in `SmlTemplate`.

### Desired Behaviour

`SmlTemplate` in the response should always contain:
1. `GeneralGEMTesting` — parsed from `general_gem_testing.txt` in `GEMTestScriptTemplates/`
2. `ToolCharacterisationTesting` — parsed from `tool_characterisation_testing.txt` in `GEMTestScriptTemplates/`
3. One additional key per user-uploaded SML file, keyed by the **exact filename** (e.g. `my_custom_tests.txt`), containing the parsed test list.

Parsing is already handled by `TestScriptService.parse_sml_to_tests()`.

### Changes

#### File: `source/services/storage_service.py`

Add a new method to `StorageService`:

```python
def list_user_sml_scripts(self, project_id: int) -> list[tuple[str, Path]]:
    """
    Return a list of (filename, path) tuples for every .txt file in
    ToolCharacterization/ that is NOT one of the two protected system templates.
    """
    SYSTEM_TEMPLATES = {"general_gem_testing.txt", "tool_characterisation_testing.txt"}
    tool_char_dir = self._project_dir(project_id) / self.TOOL_CHAR_DIR
    if not tool_char_dir.exists():
        return []
    return [
        (f.name, f)
        for f in sorted(tool_char_dir.iterdir())
        if f.is_file() and f.suffix == ".txt" and f.name not in SYSTEM_TEMPLATES
    ]
```

#### File: `source/services/sml_template.py`

Add a new function `build_sml_templates(project_id, storage)` that constructs the full `SmlTemplate` dict dynamically:

```python
from source.services.test_script_service import TestScriptService

_test_script_service = TestScriptService()

def build_sml_templates(project_id: int, storage) -> dict:
    """
    Build the SmlTemplate dict for a project response.
    Always contains the two system templates.
    Appends any user-uploaded SML scripts found in ToolCharacterization/.
    Keys for user scripts are the exact filename (e.g. 'my_script.txt').
    """
    result = {
        "GeneralGEMTesting": SML_GENERAL_TEMPLATE,
        "ToolCharacterisationTesting": SML_CHARACTERISATION_TEMPLATE,
    }
    try:
        user_scripts = storage.list_user_sml_scripts(project_id)
        for filename, path in user_scripts:
            try:
                content = path.read_text(encoding="utf-8")
                parsed = _test_script_service.parse_sml_to_tests(content)
                result[filename] = parsed
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to parse user SML script %s: %s", filename, e
                )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "Failed to list user SML scripts for project %s: %s", project_id, e
        )
    return result
```

#### File: `source/services/document_service.py`

In `_build_extraction_response()` and `_build_failed_response()`, replace all occurrences of:

```python
from source.services.sml_template import SML_TEMPLATES
...
"SmlTemplate": SML_TEMPLATES,
```

with:

```python
from source.services.sml_template import build_sml_templates
...
"SmlTemplate": build_sml_templates(project_id, self.storage),
```

#### File: `source/routers/project_routes.py`

In `ProjectAPI._build_clean_aggregated()` and any place where `SmlTemplate` is set from `SML_TEMPLATES`, replace the import and usage similarly:

```python
from source.services.sml_template import build_sml_templates
...
SmlTemplate=build_sml_templates(project_id, self.storage),
```

Search for all occurrences of `SML_TEMPLATES` across the entire `source/` directory and replace with `build_sml_templates(project_id, self.storage)`. The `project_id` is always in scope at all call sites.

---

## Work Item 3 — Remove Stale Document Categories, Add Log Files

### Document Categories to Remove

Remove the following values from the `DocumentCategory` enum in `source/schemas/project.py`:

- `COMMUNICATION_LOGS = "Communication Logs"` — being replaced by Log Files below
- `EQUIPMENT_DATA = "Equipment Data"` — vague, overlaps everything, unused
- `SECS_GEM_SCRIPTS = "SECS GEM Scripts"` — duplicate of `SML_SCRIPTS`

Keep all others including `MISCELLANEOUS`.

### Document Category to Add

Add:

```python
LOG_FILES = "Log Files"
```

### Full Updated Enum

```python
class DocumentCategory(str, Enum):
    USER_MANUALS = "User Manuals"
    TROUBLESHOOTING_GUIDANCE = "Troubleshooting Guidance"
    GEM_MANUAL = "GEM Manual"
    VARIABLE_FILES = "Variable Files"
    LOG_FILES = "Log Files"
    ALARM_FILES = "Alarm Files"
    SML_SCRIPTS = "SML Scripts"
    MISCELLANEOUS = "Miscellaneous"
```

### Log File Processing Behaviour

Log files (`.txt` extension, category `Log Files`) are **RAG-only** — they are indexed into the vector store for `/Ask` queries but do NOT contribute SVIDs, CEIDs, alarms, or any other structured data to `project_batch.json`.

#### File: `source/services/document_strategies.py`

Add a new strategy class `LogFileProcessingStrategy` after `TextProcessingStrategy`:

```python
class LogFileProcessingStrategy(DocumentProcessingStrategy):
    """
    Strategy for SECS/GEM communication log files (.txt).
    Purpose: RAG indexing only. No structured extraction.
    """
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
            doc_type_val = (
                document.DocumentType.value
                if hasattr(document.DocumentType, "value")
                else str(document.DocumentType)
            )
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
        """Index log file content into the RAG vector store for /Ask queries."""
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
            import logging
            logging.getLogger(__name__).info(
                "Indexed log file %s into RAG store at %s", document.FileName, store_path
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to index log file %s: %s", document.FileName, e
            )
```

#### File: `source/services/document_strategies.py` — `DocumentProcessorFactory`

Update `get_strategy()` to distinguish between `.txt` files that are SML scripts and `.txt` files that are log files. The distinction is made by the `document_type` passed in at upload time. Since the factory only receives a filename, we need to pass the document category through.

**Change the factory signature** to accept an optional `doc_category` parameter:

```python
class DocumentProcessorFactory:
    @staticmethod
    def get_strategy(filename: str, doc_category=None) -> DocumentProcessingStrategy:
        from source.schemas.project import DocumentCategory
        ext = Path(filename).suffix.lower()
        if ext == ".pdf":
            return PdfProcessingStrategy()
        elif ext == ".xlsx":
            return ExcelProcessingStrategy()
        elif ext == ".txt":
            # Distinguish log files from SML scripts by category
            if doc_category == DocumentCategory.LOG_FILES or (
                hasattr(doc_category, "value") and doc_category.value == "Log Files"
            ):
                return LogFileProcessingStrategy()
            return TextProcessingStrategy()
        else:
            raise ValueError(f"Unsupported file extension: {ext}")
```

#### File: `source/services/document_service.py`

In `upload_document()` and `analyze_document()`, pass `doc_category` to `DocumentProcessorFactory.get_strategy()`:

```python
# In upload_document():
strategy = DocumentProcessorFactory.get_strategy(filename, doc_category=doc_category)

# In analyze_document():
strategy = DocumentProcessorFactory.get_strategy(document.FileName, doc_category=document.DocumentType)
```

#### File: `source/schemas/project.py` — `DocumentMetadata.coerce_document_type`

Add mapping for the new type:

```python
"log file": DocumentCategory.LOG_FILES,
"log files": DocumentCategory.LOG_FILES,
```

---

## Work Item 4 — Demo PDF: Plasma Etch Tool SECS/GEM Spec

### What to Create

A single realistic-looking SECS/GEM interface specification PDF for a fictional plasma etch tool called **ETCH-Z500** by a fictional manufacturer **NanoDyne Systems**. The document should be 7–9 pages, structured like a real GEM ICD, with enough data for the demo to show:

- Upload succeeds for a PDF document
- Analyze extracts meaningful SVIDs, DVs, events, alarms, RCMDs, and state machine
- AutoMap finds plausible MES tag matches
- Ask answers questions about the equipment

### Content Requirements

The document must contain the following tables with real numeric IDs (not placeholder text), because the extraction LLM specifically looks for IDs in tables:

**Status Variables (at least 12):**

| SVID | Name | Type | Unit | Description |
|------|------|------|------|-------------|
| 1001 | SystemStatus | STRING | — | IDLE, PROCESSING, FAULT, MAINTENANCE |
| 1002 | ControlState | U1 | — | GEM control state 1–5 |
| 1003 | ChamberPressure | FLOAT | mTorr | Process chamber pressure |
| 1004 | ChamberTemperature | FLOAT | °C | Chamber wall temperature |
| 1005 | RFPower_Forward | FLOAT | W | Forward RF power to plasma |
| 1006 | RFPower_Reflected | FLOAT | W | Reflected RF power |
| 1007 | BiasVoltage | FLOAT | V | DC bias voltage on chuck |
| 1008 | GasFlow_CF4 | FLOAT | sccm | CF4 etch gas flow rate |
| 1009 | GasFlow_O2 | FLOAT | sccm | O2 additive gas flow rate |
| 1010 | GasFlow_Ar | FLOAT | sccm | Argon carrier gas flow rate |
| 1011 | WaferPresent | BOOLEAN | — | TRUE if wafer on chuck |
| 1012 | WaferID | STRING | — | Current wafer ID from OCR |
| 1013 | EMOStatus | BOOLEAN | — | Emergency Master Off state |
| 1014 | PumpStatus | STRING | — | Pump state: OFF/STARTING/RUNNING/FAULT |

**Data Variables (at least 8):**

| DVID | Name | Type | Unit | Description |
|------|------|------|------|-------------|
| 2001 | RecipeID | STRING | — | Active recipe name |
| 2002 | LotID | STRING | — | Current lot identifier |
| 2003 | WaferID_Processed | STRING | — | Wafer ID last processed |
| 2004 | EtchDepth | FLOAT | nm | Measured etch depth post-process |
| 2005 | EtchRate | FLOAT | nm/min | Calculated etch rate |
| 2006 | EtchTime_Actual | FLOAT | sec | Actual elapsed etch duration |
| 2007 | Uniformity | FLOAT | % | Within-wafer etch uniformity |
| 2008 | ProcessResult | STRING | — | PASS / FAIL / ABORTED |

**Collection Events (at least 8):**

| CEID | Name | Linked VIDs | Trigger |
|------|------|-------------|---------|
| 3001 | ProcessStart | 1001,1003,1004,2001,2002 | Etch step begins |
| 3002 | ProcessEnd | 2004,2005,2006,2008 | Etch step ends |
| 3003 | ProcessAbort | 1001,2008 | Process aborted |
| 3004 | PlasmaIgnition | 1005,1006 | RF plasma ignited |
| 3005 | PlasmaExtinguish | 1005 | RF plasma off |
| 3006 | WaferLoaded | 1011,1012 | Wafer placed on chuck |
| 3007 | WaferUnloaded | 1011,2008 | Wafer removed from chuck |
| 3008 | AlarmSet | 1001 | Any alarm became active |

**Alarms (at least 6):**

| AlarmID | Name | Severity | Linked SVID | Description |
|---------|------|----------|-------------|-------------|
| 4001 | OverPressure | critical | 1003 | Chamber pressure exceeds limit |
| 4002 | PlasmaFailure | critical | 1005,1006 | Plasma failed to ignite |
| 4003 | EMO_Activated | critical | 1013 | Emergency stop activated |
| 4004 | PressureInstability | warning | 1003 | Pressure fluctuating >5% |
| 4005 | RF_HighReflection | warning | 1006 | Reflected power >10% of forward |
| 4006 | GasFlowDeviation | warning | 1008 | CF4 flow deviation >5% from setpoint |

**Remote Commands (at least 5):**

| RCMD | Description | Parameters |
|------|-------------|------------|
| START_PROCESS | Start etch process | RECIPE_ID, WAFER_ID |
| ABORT_PROCESS | Abort active process | — |
| PAUSE_PROCESS | Pause at end of current step | — |
| RESUME_PROCESS | Resume paused process | — |
| ENTER_MAINTENANCE | Enter maintenance mode | — |
| EXIT_MAINTENANCE | Exit maintenance mode | — |

**State Machine (at least 6 states):**

States: IDLE → PUMPING → PURGE → PROCESSING → COMPLETED → IDLE, with FAULT reachable from PROCESSING/PURGE.

### File to Generate

Generate a Python script that uses `reportlab` to produce this PDF. Run it and save the output to `/mnt/user-data/outputs/ETCH_Z500_GEM_Spec_Demo.pdf`.

The PDF should look professional: use a title page, chapter headings, formatted tables with alternating row shading, and a document number. Target 8 pages.

---

## Summary of Files Changed

| Work Item | Files Modified |
|-----------|---------------|
| 1 — SML template protection | `source/services/project_service.py` |
| 2 — Dynamic SmlTemplate in response | `source/services/sml_template.py`, `source/services/storage_service.py`, `source/services/document_service.py`, `source/routers/project_routes.py` |
| 3 — Document categories + Log Files | `source/schemas/project.py`, `source/services/document_strategies.py`, `source/services/document_service.py` |
| 4 — Demo PDF | New file: `demo_docs/ETCH_Z500_GEM_Spec_Demo.pdf` (generated by script, not committed to source) |

## Implementation Order

Do items in this order to avoid broken imports:
1. Work Item 3 (schema changes first — everything depends on `DocumentCategory`)
2. Work Item 1 (project_service fix — simple, isolated)
3. Work Item 2 (sml_template refactor — depends on storage_service)
4. Work Item 4 (demo PDF — standalone, no dependencies)
