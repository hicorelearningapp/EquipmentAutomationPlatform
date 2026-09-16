"""EAP from the command line: every endpoint of the backend, with no web server.

    python eap_cli.py GET /GetAllProjects
    python eap_cli.py GET /LoadProject/12
    python eap_cli.py POST /CreateProject "{\"ProjectName\": \"Demo\", \"VendorName\": \"HiCore\", \"ProjectCode\": \"D-1\"}"
    python eap_cli.py POST /CreateProject @create_project.json
    python eap_cli.py POST /UploadDocument/12 --form document_type="GEM Manual" --file file=C:\\Docs\\manual.pdf
    python eap_cli.py --list

Starting up takes a few seconds, and the command above pays it every time. That is fine for
trying things out, but not for an application, so BraceLink starts it once and keeps it open:

    python eap_cli.py --serve

It then sends one JSON request per line and reads one JSON answer per line, each answer
costing hundredths of a second. Both ways run the same endpoints through the same object.

The paths are the same ones BraceLink calls today. The answer is printed as JSON:

    {"status": 200, "body": {...}}

and the exit code is 0 for success, 1 when the backend answered with an error, 2 when the
command itself was wrong.

How it is built
---------------
`EapCommandLine` has one method per endpoint. Each method calls the code that endpoint already
used - the router classes in source/routers and the services behind them - so no endpoint logic
is copied here. `ENDPOINTS` is the switch: it maps each method and path to its function, and
says what the request body must look like and how the answer is shaped.

The answers match the FastAPI server exactly: same field names, same status codes, same error
bodies. That matters because BraceLink's JSON reader silently leaves a field empty when a name
changes, so a mismatch would break screens without any error.

Settings come from environment variables:

    EAP_DATA_DIR    where projects, MES templates and logs are kept
                    (default: %LOCALAPPDATA%\\HiCore\\BraceLink)
    LLM_PROVIDER, LLM_MODEL_NAME, GROQ_API_KEY
                    the AI service. Without a key the backend still starts; only AI features fail.
    EAP_VERBOSE=1   also show the backend's log lines, which otherwise go to logs\\console.log
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import inspect
import io
import json
import logging
import os
import re
import sys
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, unquote, urlsplit

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


# ═════════════════════════════════════════════════════════════════════════════════════════
# The endpoints
# ═════════════════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Endpoint:
    function: Callable
    body: Any = None             # the shape the request body must have, if it takes one
    body_required: bool = True
    response: Any = None         # the shape the answer is filtered through, as FastAPI did
    status: int = 200


@dataclass
class UploadedFile:
    """A file given on the command line with --file field=path."""
    filename: str
    content: bytes


class EapCommandLine:
    """One method per endpoint, each calling the existing backend code."""

    def __init__(self) -> None:
        from source.routers.equipment_routes import EquipmentAPI
        from source.routers.mapping_routes import MappingAPI
        from source.routers.mes_family_routes import mes_family_api
        from source.routers.project_routes import ProjectAPI
        from source.routers.smart_automation_routes import SmartAutomationAPI
        from source.routers.tool_characterization_routes import ToolCharacterizationAPI
        from source.services.mes_family_seed import seed_mes_families

        self.projects = ProjectAPI()
        self.documents = EquipmentAPI()
        self.mapping = MappingAPI()
        self.mes = mes_family_api
        self.tools = ToolCharacterizationAPI()
        self.smart = SmartAutomationAPI()

        seed_mes_families()  # what the server did on startup
        _load_native_libraries()
        self.endpoints = self._build_switch()

    def _build_switch(self) -> dict[tuple[str, str], Endpoint]:
        from source.routers.mes_family_routes import MesFamilySchema
        from source.schemas.codegen import ScriptUpdateRequest, SmartCodeGenerateRequest, SmartCodeUpdateRequest
        from source.schemas.mapping import SaveMappingRequest
        from source.schemas.project import (
            AskRequest, GenerateReportsRequest, ProjectCreate, ProjectDetail,
            ProjectDetailsResponse, ProjectOut, ProjectUpdate, SystemSummaryResponse,
        )
        from source.schemas.test_script import GenerateTestScriptsRequest

        return {
            # Projects
            ("POST", "/CreateProject"): Endpoint(self.create_project, body=ProjectCreate, response=ProjectOut, status=201),
            ("GET", "/GetAllProjects"): Endpoint(self.get_all_projects, response=dict[str, list[ProjectOut]]),
            ("GET", "/LoadProject/{project_id}"): Endpoint(self.load_project, response=ProjectDetail),
            ("PUT", "/UpdateProject/{project_id}"): Endpoint(self.update_project, body=ProjectUpdate, response=ProjectOut),
            ("DELETE", "/DeleteProject/{project_id}"): Endpoint(self.delete_project),
            ("POST", "/ReAnalyzeProject/{project_id}"): Endpoint(self.reanalyze_project, response=ProjectDetail),
            ("GET", "/GetKnowledgeCategory/{project_id}"): Endpoint(self.get_knowledge_category, response=list[str]),
            ("POST", "/Ask/{project_id}"): Endpoint(self.ask, body=AskRequest),
            ("GET", "/GetProjectDetails/{project_id}"): Endpoint(self.get_project_details, response=ProjectDetailsResponse),
            ("GET", "/GetSystemSummary"): Endpoint(self.get_system_summary, response=SystemSummaryResponse),
            # Documents and extraction
            ("POST", "/UploadDocument/{project_id}"): Endpoint(self.upload_document),
            ("GET", "/Analyze/{project_id}/{document_id}/report"): Endpoint(self.download_report),
            ("GET", "/Analyze/{project_id}/{document_id}"): Endpoint(self.analyze_document),
            ("GET", "/AnalyzeProject/{project_id}"): Endpoint(self.analyze_project),
            ("GET", "/GetVariable/{project_id}/{document_id}"): Endpoint(self.get_variable),
            ("DELETE", "/DeleteDocument/{project_id}/{document_id}"): Endpoint(self.delete_document),
            ("POST", "/UpdateExtraction/{project_id}"): Endpoint(self.update_extraction, body=dict),
            ("POST", "/GenerateReports/{project_id}"): Endpoint(self.generate_reports, body=GenerateReportsRequest, body_required=False),
            ("PUT", "/UpdateReports/{project_id}"): Endpoint(self.update_reports, body=dict),
            ("GET", "/GetQuestions/{project_id}"): Endpoint(self.get_questions),
            # Mapping
            ("PUT", "/UpdateMapping/{project_id}"): Endpoint(self.update_mapping, body=SaveMappingRequest),
            ("POST", "/AutoMap"): Endpoint(self.auto_map, body=dict),
            # MES families and templates
            ("GET", "/GetMesFamilies"): Endpoint(self.get_mes_families),
            ("POST", "/UpdateMesFamilies"): Endpoint(self.update_mes_families, body=list[MesFamilySchema]),
            ("GET", "/GetMesTemplates/{mes_family}"): Endpoint(self.get_mes_templates),
            ("GET", "/GetMesTemplateInfo/{mes_family}/{template}"): Endpoint(self.get_mes_template_info),
            ("POST", "/AddMesTemplateInfo/{mes_family}"): Endpoint(self.add_mes_template_info),
            ("PUT", "/UpdateMesTemplateInfo/{mes_family}/{template}"): Endpoint(self.update_mes_template_info),
            # Tool characterization
            ("POST", "/GenerateTestScripts/{project_id}"): Endpoint(self.generate_test_scripts, body=GenerateTestScriptsRequest),
            ("POST", "/UpdateToolCharacterizationScript/{project_id}"): Endpoint(self.update_tool_characterization_script, body=ScriptUpdateRequest),
            ("POST", "/GenerateSMLScripts/{project_id}"): Endpoint(self.generate_sml_scripts),
            ("POST", "/UploadTestResult"): Endpoint(self.upload_test_result),
            ("GET", "/GetToolResults/{project_id}"): Endpoint(self.get_tool_results),
            # Smart automation
            ("POST", "/GenerateSmartAutomationCode/{project_id}"): Endpoint(self.generate_smart_automation_code, body=SmartCodeGenerateRequest),
            ("POST", "/UpdateSmartAutomationCode/{project_id}"): Endpoint(self.update_smart_automation_code, body=SmartCodeUpdateRequest),
            ("POST", "/GenerateOverallReport/{project_id}"): Endpoint(self.generate_overall_report),
            # Service check
            ("GET", "/health"): Endpoint(self.health),
        }

    # ── Projects ────────────────────────────────────────────────────────────────────────

    def create_project(self, body):
        """Create a project."""
        return self.projects.create_project(body)

    def get_all_projects(self):
        """List every project: {"ProjectInfo": [...]}."""
        return self.projects.list_projects()

    def load_project(self, project_id: int):
        """A project with its documents, extractions, mappings, script templates and questions."""
        return self.projects.load_project(project_id)

    def update_project(self, project_id: int, body):
        """Change a project's name, vendor, code or description."""
        return self.projects.update_project(project_id, body)

    def delete_project(self, project_id: int):
        """Delete a project and everything in it."""
        return self.projects.delete_project(project_id)

    def reanalyze_project(self, project_id: int):
        """Run extraction again over all of a project's documents."""
        return self.projects.reanalyze_project(project_id)

    def get_knowledge_category(self, project_id: int):
        """The document categories that have searchable content."""
        return self.projects.get_knowledge_category(project_id)

    def ask(self, project_id: int, body):
        """Answer a question from the project's documents."""
        return self.projects.ask_project(project_id, body)

    def get_project_details(self, project_id: int):
        """Counts for one project: documents, status variables, data variables, remote commands."""
        return self.projects.get_project_details(project_id)

    def get_system_summary(self):
        """Totals across all projects."""
        return self.projects.get_system_summary()

    # ── Documents and extraction ────────────────────────────────────────────────────────

    def upload_document(self, project_id: int, file: UploadedFile, document_type: str):
        """Add a document to a project (--file file=path --form document_type=...)."""
        from source.schemas.project import DocumentCategory
        return _run(self.documents.upload_document(project_id, _as_upload(file), DocumentCategory(document_type)))

    def download_report(self, project_id: int, document_id: str):
        """A document's extraction as a JSON file."""
        return self.documents.download_report(project_id, document_id)

    def analyze_document(self, project_id: int, document_id: str):
        """Extract equipment data from one document."""
        return self.documents.analyze(project_id, document_id)

    def analyze_project(self, project_id: int):
        """Extract from every pending document and merge the results."""
        return self.documents.analyze_project(project_id)

    def get_variable(self, project_id: int, document_id: str, categories: Optional[str] = None):
        """A document's variables, optionally only some categories (?categories=...)."""
        return self.documents.get_variable(project_id, document_id, categories)

    def delete_document(self, project_id: int, document_id: str):
        """Remove a document and its search index entries."""
        return self.documents.delete_document(project_id, document_id)

    def update_extraction(self, project_id: int, body):
        """Save edited status variables, events, alarms, commands and reports."""
        return self.documents.update_extraction(project_id, body)

    def generate_reports(self, project_id: int, body):
        """Propose event reports, optionally for chosen CEIDs only."""
        return self.documents.generate_reports(project_id, body)

    def update_reports(self, project_id: int, body):
        """Save edited reports."""
        return self.documents.update_reports(project_id, body)

    def get_questions(self, project_id: int):
        """The predefined questions and their answers."""
        return self.documents.get_questions(project_id)

    # ── Mapping ─────────────────────────────────────────────────────────────────────────

    def update_mapping(self, project_id: int, body):
        """Save approved MES mappings into the chosen template."""
        return self.mapping.update_mapping(project_id, body)

    def auto_map(self, project_id: int, body):
        """Suggest equipment matches for MES tags (?project_id=...)."""
        return self.mapping.auto_map(project_id, body)

    # ── MES families and templates ──────────────────────────────────────────────────────

    def get_mes_families(self):
        return self.mes.get_mes_families()

    def update_mes_families(self, body):
        return self.mes.update_mes_families(body)

    def get_mes_templates(self, mes_family: str):
        return self.mes.get_mes_templates(mes_family)

    def get_mes_template_info(self, mes_family: str, template: str):
        return self.mes.get_mes_template_info(mes_family, template)

    def add_mes_template_info(self, mes_family: str, file: UploadedFile):
        """Add a template file to a family (--file file=path)."""
        return _run(self.mes.add_mes_template_info(mes_family, _as_upload(file)))

    def update_mes_template_info(self, mes_family: str, template: str, file: UploadedFile):
        """Replace a template file (--file file=path)."""
        return _run(self.mes.update_mes_template_info(mes_family, template, _as_upload(file)))

    # ── Tool characterization ───────────────────────────────────────────────────────────

    def generate_test_scripts(self, project_id: int, body):
        return self.tools.generate_test_scripts(project_id, body)

    def update_tool_characterization_script(self, project_id: int, body):
        return self.tools.update_tool_char_script(project_id, body)

    def generate_sml_scripts(self, project_id: int):
        return self.tools.generate_sml_scripts(project_id)

    def upload_test_result(self, project_id: int, tool_id: str, files: list[UploadedFile]):
        """Store test results (--form project_id=... --form tool_id=... --file files=path)."""
        return _run(self.tools.upload_test_result(project_id, tool_id, [_as_upload(f) for f in files]))

    def get_tool_results(self, project_id: int, tool_id: str):
        """Stored test runs for a tool (?tool_id=...)."""
        return _run(self.tools.get_tool_results(project_id, tool_id))

    # ── Smart automation ────────────────────────────────────────────────────────────────

    def generate_smart_automation_code(self, project_id: int, body):
        return self.smart.generate_smart_automation_code(project_id, body)

    def update_smart_automation_code(self, project_id: int, body):
        return self.smart.update_smart_automation_code(project_id, body)

    def generate_overall_report(self, project_id: int):
        return self.smart.generate_overall_report(project_id)

    # ── Service check ───────────────────────────────────────────────────────────────────

    def health(self):
        return {"status": "ok"}

    # ═════════════════════════════════════════════════════════════════════════════════════
    # Finding the endpoint and shaping the answer - what FastAPI used to do
    # ═════════════════════════════════════════════════════════════════════════════════════

    def handle(self, method: str, path: str, body: Any = None, form: Optional[dict] = None,
               files: Optional[list[tuple[str, UploadedFile]]] = None) -> dict:
        """Run one request. Returns {"status": ..., "body": ...} or {"status", "text", "headers"}."""
        from fastapi import HTTPException

        split = urlsplit(path)
        query = {k: v[-1] for k, v in parse_qs(split.query).items()}
        endpoint, path_values, known_path = self._find(method.upper(), split.path)
        if endpoint is None:
            return ({"status": 405, "body": {"detail": "Method Not Allowed"}} if known_path
                    else {"status": 404, "body": {"detail": "Not Found"}})

        try:
            arguments = self._arguments(endpoint, path_values, query, body, form or {}, files or [])
        except _Invalid as invalid:
            return {"status": 422, "body": {"detail": invalid.errors}}

        try:
            result = endpoint.function(**arguments)
        except HTTPException as error:
            return {"status": error.status_code, "body": {"detail": _jsonable(error.detail)}}
        except Exception:
            logging.getLogger(__name__).exception("Unhandled error in %s %s", method, path)
            return {"status": 500, "text": "Internal Server Error"}

        return self._answer(endpoint, result)

    def _find(self, method: str, path: str):
        known_path = False
        for (route_method, template), endpoint in self.endpoints.items():
            match = _pattern(template).match(path)
            if not match:
                continue
            known_path = True
            if route_method == method:
                return endpoint, {k: unquote(v) for k, v in match.groupdict().items()}, True
        return None, {}, known_path

    def _arguments(self, endpoint: Endpoint, path_values: dict, query: dict, body: Any,
                   form: dict, files: list) -> dict:
        from pydantic import TypeAdapter, ValidationError

        uploads: dict[str, list[UploadedFile]] = {}
        for field, uploaded in files:
            uploads.setdefault(field, []).append(uploaded)

        arguments, errors = {}, []
        for name, parameter in inspect.signature(endpoint.function).parameters.items():
            annotation = parameter.annotation
            if name == "body":
                if body is None and endpoint.body_required:
                    errors.append({"type": "missing", "loc": ["body"], "msg": "Field required", "input": None})
                    continue
                value = body if body is not None else {}
                if endpoint.body in (dict, None):
                    arguments[name] = value
                    continue
                try:
                    arguments[name] = TypeAdapter(endpoint.body).validate_python(value)
                except ValidationError as error:
                    errors += [_error(e, "body") for e in error.errors()]
                continue

            if name in uploads:
                many = str(annotation).startswith("list")
                arguments[name] = uploads[name] if many else uploads[name][0]
                continue

            for source, values in (("path", path_values), ("body", form), ("query", query)):
                if name in values:
                    try:
                        arguments[name] = TypeAdapter(_plain_type(annotation)).validate_python(values[name])
                    except ValidationError as error:
                        errors += [_error(e, source, name, values[name]) for e in error.errors()]
                    break
            else:
                if parameter.default is not inspect.Parameter.empty:
                    arguments[name] = parameter.default
                else:
                    where = "query" if name in ("tool_id", "project_id") and not path_values else "body"
                    errors.append({"type": "missing", "loc": [where, name], "msg": "Field required", "input": None})

        if errors:
            raise _Invalid(errors)
        return arguments

    def _answer(self, endpoint: Endpoint, result: Any) -> dict:
        from fastapi.responses import Response
        from pydantic import BaseModel, TypeAdapter

        if isinstance(result, Response):  # a file, such as an extraction report
            headers = {k: v for k, v in result.headers.items() if k.lower() == "content-disposition"}
            return {"status": endpoint.status, "text": result.body.decode("utf-8"), "headers": headers}
        if endpoint.response is not None:
            adapter = TypeAdapter(endpoint.response)
            value = adapter.validate_python(result.model_dump() if isinstance(result, BaseModel) else result)
            return {"status": endpoint.status, "body": adapter.dump_python(value, mode="json", by_alias=False)}
        return {"status": endpoint.status, "body": _jsonable(result)}


# ═════════════════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════════════════

class _Invalid(Exception):
    def __init__(self, errors: list):
        super().__init__("invalid request")
        self.errors = errors


def _pattern(template: str) -> re.Pattern:
    escaped = re.escape(template).replace(r"\{", "{").replace(r"\}", "}")
    return re.compile("^" + re.sub(r"\{([^}]+)\}", r"(?P<\1>[^/]+)", escaped) + "$")


def _plain_type(annotation: Any) -> Any:
    return str if annotation in (inspect.Parameter.empty, Any) else annotation


def _error(error: dict, source: str, name: Optional[str] = None, value: Any = None) -> dict:
    """A validation error in the shape FastAPI returned."""
    location = [source] + ([name] if name else []) + [str(part) for part in error.get("loc", ())]
    return {"type": error.get("type"), "loc": location, "msg": error.get("msg"),
            "input": _jsonable(value if name else error.get("input"))}


def _jsonable(value: Any) -> Any:
    from fastapi.encoders import jsonable_encoder  # exactly what FastAPI used for answers
    return jsonable_encoder(value)


def _run(result: Any) -> Any:
    """Some endpoint functions are async; run them to completion."""
    return asyncio.run(result) if inspect.isawaitable(result) else result


def _as_upload(uploaded: UploadedFile):
    from fastapi import UploadFile
    return UploadFile(file=io.BytesIO(uploaded.content), filename=uploaded.filename)


def _load_native_libraries() -> None:
    """Load the libraries written in C while starting, on the main thread.

    In --serve mode requests run on worker threads, and loading one of these there can hang
    on Windows: the search index (faiss) was seen to stop halfway through loading and never
    finish. Loading them here avoids that, and makes the first request faster.
    """
    import faiss  # noqa: F401  (the document search index)
    import fitz  # noqa: F401  (reading PDFs)
    import pdfplumber  # noqa: F401  (reading tables out of PDFs)

    from source.utils.embedder import VectorStoreManager

    VectorStoreManager.get_embeddings()  # opens the embedding model


# ═════════════════════════════════════════════════════════════════════════════════════════
# Staying open for BraceLink (--serve)
# ═════════════════════════════════════════════════════════════════════════════════════════

PROTOCOL_VERSION = "1.0"
DEFAULT_WORKERS = 8


class RequestLoop:
    """Reads requests from BraceLink and writes back answers.

    One JSON object per line, in both directions, encoded as UTF-8. Requests are handled on
    several threads, so a long analysis does not block the rest of the screens; answers can
    therefore come back in a different order, and BraceLink matches them by their id.

        in :  {"id": "42", "method": "GET", "path": "/LoadProject/12"}
        out:  {"id": "42", "status": 200, "body": {...}}

    Uploads arrive either as a path to a file on disk or as the content itself:

        {"id": "43", "method": "POST", "path": "/UploadDocument/12",
         "form": {"document_type": "GEM Manual"},
         "files": [{"field": "file", "path": "C:\\\\Docs\\\\manual.pdf"}]}
        {"id": "44", ... "files": [{"field": "files", "filename": "Test_x.json",
                                    "content_base64": "..."}]}

    When the input closes - including when BraceLink stops or crashes - the loop ends and the
    program exits.
    """

    def __init__(self, cli: Optional[EapCommandLine], output, workers: int = DEFAULT_WORKERS):
        self._cli = cli
        self._output = output
        self._workers = workers
        self._write_lock = threading.Lock()

    # ── Writing ─────────────────────────────────────────────────────────────────────────

    def send(self, message: dict) -> None:
        """One message per line. The lock keeps answers from different threads apart."""
        line = json.dumps(message, ensure_ascii=False, default=str)
        with self._write_lock:
            self._output.write(line + "\n")
            self._output.flush()

    def announce_ready(self) -> None:
        self.send({"type": "ready", "version": PROTOCOL_VERSION})

    def announce_fatal(self, detail: str) -> None:
        self.send({"type": "fatal", "detail": detail})

    # ── Reading ─────────────────────────────────────────────────────────────────────────

    def run(self, source) -> None:
        with ThreadPoolExecutor(max_workers=self._workers, thread_name_prefix="request") as pool:
            for line in source:
                line = line.strip()
                if not line:
                    continue
                try:
                    request = json.loads(line)
                except json.JSONDecodeError as error:
                    self.send({"id": None, "status": 400,
                               "body": {"detail": f"Could not read the request: {error}"}})
                    continue
                if not isinstance(request, dict):
                    self.send({"id": None, "status": 400,
                               "body": {"detail": "A request must be a JSON object"}})
                    continue
                if request.get("type") == "shutdown":
                    logging.getLogger(__name__).info("Shutdown requested")
                    break
                pool.submit(self._handle, request)
        logging.getLogger(__name__).info("Input closed; the backend is stopping")

    # ── Handling one request ────────────────────────────────────────────────────────────

    def _handle(self, request: dict) -> None:
        request_id = request.get("id")
        try:
            answer = self._cli.handle(
                method=request.get("method", "GET"),
                path=request.get("path", ""),
                body=request.get("body"),
                form=request.get("form") or {},
                files=[_to_uploaded_file(entry) for entry in request.get("files") or []],
            )
            self.send({"id": request_id, **answer})
        except Exception as error:  # a fault here must not take the backend down
            logging.getLogger(__name__).exception("Failed to handle request %s", request_id)
            self.send({"id": request_id, "status": 500,
                       "body": {"detail": f"Internal Server Error: {error}"}})


def _to_uploaded_file(entry: dict) -> tuple[str, UploadedFile]:
    field = entry.get("field", "file")
    if entry.get("path"):
        path = Path(entry["path"])
        return field, UploadedFile(filename=entry.get("filename") or path.name,
                                   content=path.read_bytes())
    content: Optional[str] = entry.get("content_base64")
    if content is not None:
        return field, UploadedFile(filename=entry.get("filename", "upload"),
                                   content=base64.b64decode(content))
    return field, UploadedFile(filename=entry.get("filename", "upload"),
                               content=(entry.get("content") or "").encode("utf-8"))


# ═════════════════════════════════════════════════════════════════════════════════════════
# Running from the command line
# ═════════════════════════════════════════════════════════════════════════════════════════

def _prepare_environment() -> None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    default = Path(local_app_data) / "HiCore" / "BraceLink" if local_app_data else Path.home() / ".hicore"
    os.environ.setdefault("EAP_DATA_DIR", str(default))
    os.environ.setdefault("EAP_APP_DIR", str(HERE))
    token_encoding = HERE / "models" / "tiktoken_cache"  # delivered, so nothing is downloaded
    if token_encoding.is_dir():
        os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(token_encoding))


def _keep_answer_clean(verbose: bool):
    """Only the answer goes to the screen. Logs, and anything libraries print while loading,
    go to logs\\console.log unless EAP_VERBOSE is set."""
    from source.app_paths import logs_dir

    answer_stream = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(logs_dir() / "backend.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    ]
    console_log = None
    if verbose:
        os.dup2(2, 1)
        sys.stdout = sys.stderr
        handlers.append(logging.StreamHandler(sys.stderr))
    else:
        console_log = logs_dir() / "console.log"
        stream = open(console_log, "a", encoding="utf-8", buffering=1)
        os.dup2(stream.fileno(), 1)
        os.dup2(stream.fileno(), 2)
        sys.stdout = sys.stderr = stream
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s")
    logging.captureWarnings(True)
    return answer_stream, console_log


def _read_body(text: Optional[str], out) -> tuple[bool, Any]:
    if not text:
        return True, None
    if text.startswith("@"):
        body_file = Path(text[1:])
        if not body_file.is_file():
            out.write(f"the body file was not found: {body_file.resolve()}\n")
            return False, None
        text = body_file.read_text(encoding="utf-8-sig")
    try:
        return True, json.loads(text) if text.strip() else None
    except json.JSONDecodeError as error:
        out.write(f"the request body is not valid JSON ({error.msg} at character {error.pos}).\n"
                  "Usually the shell changed the quotes: put the body in a file and pass @file.json,\n"
                  "or in PowerShell wrap it in single quotes.\n")
        return False, None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="eap_cli", description="Call any EAP backend endpoint from the command line.")
    parser.add_argument("method", nargs="?", help="GET, POST, PUT or DELETE")
    parser.add_argument("path", nargs="?", help="for example /LoadProject/12")
    parser.add_argument("body", nargs="?", help="JSON text, or @file.json")
    parser.add_argument("--file", action="append", default=[], metavar="FIELD=PATH",
                        help="a file to upload; repeat for several")
    parser.add_argument("--form", action="append", default=[], metavar="KEY=VALUE",
                        help="a form field for uploads; repeat for several")
    parser.add_argument("--list", action="store_true", help="list every endpoint and exit")
    parser.add_argument("--serve", action="store_true",
                        help="stay open and answer one JSON request per line, for BraceLink")
    args = parser.parse_args(argv)

    _prepare_environment()
    # --serve writes the protocol on the answer stream, so its own logs go to the error
    # stream, where BraceLink can read them.
    out, console_log = _keep_answer_clean(verbose=args.serve or bool(os.environ.get("EAP_VERBOSE")))
    see_log = f"\ndetails: {console_log}" if console_log else ""

    if not (args.list or args.serve) and not (args.method and args.path):
        out.write("usage: eap_cli METHOD /Path [JSON | @file.json] [--file field=path] [--form key=value]\n"
                  "       eap_cli --serve\n"
                  "       eap_cli --list\n")
        return 2

    ok, body = _read_body(args.body, out)
    if not ok:
        return 2
    try:
        files = []
        for item in args.file:
            field, _, file_path = item.partition("=")
            files.append((field, UploadedFile(Path(file_path).name, Path(file_path).read_bytes())))
        form = dict(item.partition("=")[::2] for item in args.form)
    except OSError as error:
        out.write(f"could not read the file to upload: {error}\n")
        return 2

    try:
        cli = EapCommandLine()
    except Exception as error:
        traceback.print_exc()
        detail = f"{type(error).__name__}: {error}"
        if args.serve:  # BraceLink is waiting for a line, not for a sentence
            RequestLoop(None, out).announce_fatal(detail)
        else:
            out.write(f"the backend could not start: {detail}{see_log}\n")
        return 1

    if args.serve:
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8")  # BraceLink sends UTF-8, whatever the PC's locale
        loop = RequestLoop(cli, out)
        loop.announce_ready()
        logging.getLogger(__name__).info("Ready; data folder: %s", os.environ["EAP_DATA_DIR"])
        loop.run(sys.stdin)
        return 0

    if args.list:
        for method, template in cli.endpoints:
            out.write(f"{method:<7}{template}\n")
        return 0

    answer = cli.handle(args.method, args.path, body=body, form=form, files=files)
    out.write(json.dumps(answer, indent=2, ensure_ascii=False, default=str) + "\n")
    return 0 if answer["status"] < 400 else 1


if __name__ == "__main__":
    sys.exit(main())
