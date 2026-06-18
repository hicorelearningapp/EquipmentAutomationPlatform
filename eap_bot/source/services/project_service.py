import logging
from pathlib import Path
from typing import Any

from source.schemas.mapping import MESTag
from source.schemas.project import AggregatedSpec, ProjectDetail, ProjectDetailsResponse, SystemSummaryResponse
from source.schemas.secsgem import EquipmentSpec
from source.services.storage_service import (
    DocumentNotFoundError,
    InvalidSlugError,
    ProjectNotFoundError,
    StorageError,
    StorageService,
)
from source.utils.embedder import VectorStoreManager

logger = logging.getLogger(__name__)


class ProjectService:
    """Handles project-level orchestration: batch analysis, aggregation, MES mapping."""

    def __init__(self, storage: StorageService, container: Any) -> None:
        self.storage = storage
        self._container = container

    # ── Batch analysis + aggregation ─────────────────────────────────────────

    def aggregate_project_data(self, project_id: int, auto_analyze: bool = False) -> tuple[Any, AggregatedSpec]:
        """
        1. Analyse any pending documents.
        2. Aggregate + deduplicate all completed specs.
        Returns (project_metadata, aggregated_spec).
        """
        self.storage.increment_project_version(project_id)
        self.storage.write_sml_template(project_id)

        metadata = self.storage.get_project(project_id)

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

        if auto_analyze:
            # Analyse pending documents
            for doc in metadata.Documents:
                if doc.Status == "uploaded":
                    logger.info("Auto-analysing document %s for project %s", doc.DocumentID, project_id)
                    try:
                        self._container.document_service.analyze_document(project_id, doc.DocumentID)
                    except Exception as e:
                        logger.error("Failed to auto-analyse %s: %s", doc.DocumentID, e)
                        self.storage.mark_failed(project_id, doc.DocumentID)

            # Reload metadata after analysis
            metadata = self.storage.get_project(project_id)

        # Build aggregated spec
        aggregated = self._build_aggregated_spec(project_id, metadata)

        return metadata, aggregated

    def _build_aggregated_spec(self, project_id: int, metadata: Any) -> AggregatedSpec:
        aggregated = EquipmentSpec(
            DocumentType=metadata.Documents[0].DocumentType if metadata.Documents else "GEM Manual",
            ToolID=metadata.ProjectName,
            ToolType=metadata.Tool.value if hasattr(metadata, "Tool") and metadata.Tool else "Semiconductor Processing Equipment",
        )

        for doc in metadata.Documents:
            if doc.Status == "completed":
                try:
                    spec_json = self.storage.read_spec_json(project_id, doc.DocumentID)
                    spec = EquipmentSpec.model_validate_json(spec_json)
                    
                    # Merge top-level metadata if extracted (prioritize extracted over generic default)
                    if spec.ToolID and spec.ToolID.lower() not in ("string", "unknown", "none", ""):
                        aggregated.ToolID = spec.ToolID
                    if spec.ToolType and spec.ToolType.lower() not in ("string", "unknown", "none", ""):
                        aggregated.ToolType = spec.ToolType
                    if spec.Model and spec.Model.lower() not in ("string (optional)", "unknown", "none", ""):
                        aggregated.Model = spec.Model
                    if spec.Protocol and spec.Protocol.lower() not in ("string", "unknown", "none", ""):
                        aggregated.Protocol = spec.Protocol
                        
                    # Merge Summary
                    if spec.Summary:
                        if not aggregated.Summary:
                            aggregated.Summary = spec.Summary.model_copy(deep=True) if hasattr(spec.Summary, "model_copy") else spec.Summary.copy()
                        else:
                            if spec.Summary.EquipmentName and spec.Summary.EquipmentName.lower() not in ("string", "string - extract from 'project name' if specified, else generic name"):
                                aggregated.Summary.EquipmentName = spec.Summary.EquipmentName
                            if spec.Summary.WaferSize and spec.Summary.WaferSize.lower() != "string":
                                aggregated.Summary.WaferSize = spec.Summary.WaferSize
                            if spec.Summary.SoftwareRevision and spec.Summary.SoftwareRevision.lower() != "string":
                                aggregated.Summary.SoftwareRevision = spec.Summary.SoftwareRevision
                            if spec.Summary.ToolID and spec.Summary.ToolID.lower() not in ("string", "string - extract from 'project id' if specified, else tool/machine id"):
                                aggregated.Summary.ToolID = spec.Summary.ToolID
                            
                            if spec.Summary.StandardsSupported:
                                if aggregated.Summary.StandardsSupported is None:
                                    aggregated.Summary.StandardsSupported = []
                                aggregated.Summary.StandardsSupported.extend(spec.Summary.StandardsSupported)
                            if spec.Summary.GEMCompliance:
                                if aggregated.Summary.GEMCompliance is None:
                                    aggregated.Summary.GEMCompliance = []
                                aggregated.Summary.GEMCompliance.extend(spec.Summary.GEMCompliance)
                            if spec.Summary.HSMSConfiguration and not aggregated.Summary.HSMSConfiguration:
                                aggregated.Summary.HSMSConfiguration = spec.Summary.HSMSConfiguration
                            if spec.Summary.StreamFunctions:
                                if aggregated.Summary.StreamFunctions is None:
                                    aggregated.Summary.StreamFunctions = []
                                aggregated.Summary.StreamFunctions.extend(spec.Summary.StreamFunctions)
                            if spec.Summary.CommunicationStates:
                                if aggregated.Summary.CommunicationStates is None:
                                    aggregated.Summary.CommunicationStates = []
                                aggregated.Summary.CommunicationStates.extend(spec.Summary.CommunicationStates)
                            if spec.Summary.ControlStates:
                                if aggregated.Summary.ControlStates is None:
                                    aggregated.Summary.ControlStates = []
                                aggregated.Summary.ControlStates.extend(spec.Summary.ControlStates)

                    is_excel = doc.FileName.lower().endswith(".xlsx")
                    is_txt = doc.FileName.lower().endswith(".txt")
                    if not spec.Reports and not is_excel and not is_txt:
                        file_path = self._resolve_document_path(project_id, doc)
                        text = self._container.parser.extract_text(str(file_path))
                        reports = self._container.report_service.extract_builtin_reports(text)
                        if reports:
                            spec.Reports = reports
                            json_path = self.storage.spec_json_path(project_id, doc.DocumentID)
                            self.storage.save_spec_json(json_path, spec)

                    aggregated.StatusVariables.extend(spec.StatusVariables)
                    aggregated.DataVariables.extend(spec.DataVariables)
                    aggregated.Events.extend(spec.Events)
                    aggregated.Alarms.extend(spec.Alarms)
                    aggregated.RemoteCommands.extend(spec.RemoteCommands)
                    aggregated.States.extend(spec.States)
                    aggregated.StateTransitions.extend(spec.StateTransitions)
                    aggregated.Reports.extend(spec.Reports)
                except Exception as e:
                    logger.warning("Failed to read/merge spec for %s: %s", doc.DocumentID, e)
                    continue

        # Deduplicate
        aggregated.StatusVariables = self._dedup_by(aggregated.StatusVariables, "SVID")
        aggregated.DataVariables = self._dedup_by(aggregated.DataVariables, "DvID")
        aggregated.Events = self._dedup_by(aggregated.Events, "CEID")
        aggregated.Alarms = self._dedup_by(aggregated.Alarms, "AlarmID")
        aggregated.RemoteCommands = self._dedup_by(aggregated.RemoteCommands, "RCMD")
        aggregated.States = self._dedup_by(aggregated.States, "StateID")
        aggregated.StateTransitions = self._dedup_transitions(aggregated.StateTransitions)
        aggregated.Reports = self._dedup_by(aggregated.Reports, "RPTID")

        # Generate Project-level Summary Report PDF using aggregated JSON data
        self.generate_project_pdf(project_id, aggregated)

        return aggregated

    def generate_project_pdf(self, project_id: int, spec: EquipmentSpec) -> None:
        """Helper to generate the PDF report for a given spec."""
        try:
            from source.services.report_generator import ReportGenerator
            report_gen = ReportGenerator()
            report_dir = self.storage._project_dir(project_id) / "SummaryReport"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "Summary_Report.pdf"
            report_gen.generate_report(spec, report_path)
            logger.info(f"Successfully generated Project Summary Report for project {project_id}")
        except Exception as e:
            logger.error("Failed to generate Project Summary Report: %s", e)

    # ── MES Mapping ───────────────────────────────────────────────────────────

    def get_mes_mapping(self, project_id: int, body: Any) -> Any:
        spec_path = self.storage.spec_json_path(project_id, "project_batch")
        if not spec_path.exists():
            raise ProjectNotFoundError(f"Could not find batch extraction for project {project_id}")

        spec_json = spec_path.read_text(encoding="utf-8")
        spec = EquipmentSpec.model_validate_json(spec_json)

        template_filename = body.template
        if not template_filename.lower().endswith(".json"):
            template_filename = f"{template_filename}.json"

        template_path = (
            Path(__file__).resolve().parent.parent.parent
            / "MESMapTemplates"
            / body.family
            / template_filename
        )
        if not template_path.exists():
            raise FileNotFoundError(f"MES template not found at {template_path}")

        from source.utils.template_parser import _extract_tags_from_template
        import json
        with open(template_path, "r", encoding="utf-8") as f:
            raw_tags = json.load(f)
        target_tags = _extract_tags_from_template(raw_tags)

        return self._container.mapping_service.suggest_mappings(spec, target_tags)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_document_path(self, project_id: int, doc: Any) -> Path:
        ext = Path(doc.FileName).suffix.lower()
        if ext == ".xlsx":
            return self.storage.document_excel_path(project_id, doc.DocumentID, ext=".xlsx")
        elif ext == ".txt":
            return self.storage.document_excel_path(project_id, doc.DocumentID, ext=".txt")
        return self.storage.document_pdf_path(project_id, doc.DocumentID)

    @staticmethod
    def _dedup_by(items: list, key: str) -> list:
        seen = set()
        result = []
        for item in items:
            val = getattr(item, key, None) if hasattr(item, key) else item.get(key)
            if val not in seen:
                seen.add(val)
                result.append(item)
        return result

    @staticmethod
    def _dedup_transitions(items: list) -> list:
        seen = set()
        result = []
        for t in items:
            key = (
                getattr(t, "FromState", None),
                getattr(t, "ToState", None),
                getattr(t, "TriggerEvent", None),
                getattr(t, "TriggerCommand", None),
            )
            if key not in seen:
                seen.add(key)
                result.append(t)
        return result

    # ── Project Details & Summary ─────────────────────────────────────────────

    def get_project_details(self, project_id: int) -> ProjectDetailsResponse:
        metadata = self.storage.get_project(project_id)

        documents = metadata.Documents or []
        number_of_documents = len(documents)

        # Count files in ToolCharacterization folder
        tool_char_dir = self.storage._project_dir(project_id) / self.storage.TOOL_CHAR_DIR
        number_of_sml_scripts = 0
        if tool_char_dir.is_dir():
            number_of_sml_scripts = len([
                f for f in tool_char_dir.iterdir()
                if f.is_file()
            ])

        total_svs = 0
        total_dvs = 0
        total_rcmds = 0
        total_reports = 0
        total_alarms = 0
        total_events = 0

        for doc in documents:
            if doc.Status != "completed":
                continue

            try:
                spec_json = self.storage.read_spec_json(
                    project_id,
                    doc.DocumentID
                )
                spec = EquipmentSpec.model_validate_json(spec_json)

                total_svs += len(spec.StatusVariables) if spec.StatusVariables else 0
                total_dvs += len(spec.DataVariables) if spec.DataVariables else 0
                total_rcmds += len(spec.RemoteCommands) if spec.RemoteCommands else 0
                total_reports += len(spec.Reports) if spec.Reports else 0
                total_alarms += len(spec.Alarms) if spec.Alarms else 0
                total_events += len(spec.Events) if spec.Events else 0

            except Exception:
                continue

        return ProjectDetailsResponse(
            Id=metadata.ProjectID,
            ProjectName=metadata.ProjectName,
            ProjectCode=metadata.ProjectCode,
            ProjectDescription=metadata.ProjectDescription,
            VendorName=metadata.VendorName if metadata.VendorName else None,
            Tool=(
                metadata.Tool.value
                if hasattr(metadata.Tool, "value") else (metadata.Tool if metadata.Tool else None)
            ),
            ProjectVersion=getattr(metadata, "ProjectVersion", None),
            CreatedAt=metadata.CreatedAt,
            DocumentCount=number_of_documents,
            SVCount=total_svs,
            DVCount=total_dvs,
            RCCount=total_rcmds,
            SmlScriptCount=number_of_sml_scripts,
            ReportCount=total_reports,
            AlarmCount=total_alarms,
            EventCount=total_events,
        )

    def get_system_summary(self) -> SystemSummaryResponse:
        projects = self.storage.list_projects()
        total_sml = 0
        total_tools = 0
        total_scripts_tested = 0
        
        for project in projects:
            tool_char_dir = self.storage._project_dir(project.ProjectID) / self.storage.TOOL_CHAR_DIR
            if tool_char_dir.is_dir():
                total_sml += len([f for f in tool_char_dir.iterdir() if f.is_file()])
            
            results_dir = self.storage._project_dir(project.ProjectID) / self.storage.RESULTS_DIR
            if results_dir.is_dir():
                total_scripts_tested += len(list(results_dir.rglob("*.txt")))
            
            try:
                total_tools += self.storage.count_connected_equipments(project.ProjectID)
            except Exception:
                pass
                
        return SystemSummaryResponse(
            TotalProjects=len(projects),
            TotalSmlScripts=total_sml,
            TotalConnectedTools=total_tools,
            TotalScriptsTested=total_scripts_tested,
        )
