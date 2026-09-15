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

    def get_knowledge_category_workflow(self, project_id: int) -> list[str]:
        self.storage.get_project(project_id)
        return self.storage.get_populated_categories(project_id)

    def load_project_workflow(self, project_id: int) -> dict:
        batch_path = self.storage.spec_json_path(project_id, "project_batch")
        if batch_path.exists():
            from source.schemas.secsgem import EquipmentSpec
            aggregated = EquipmentSpec.model_validate_json(batch_path.read_text(encoding="utf-8"))
        else:
            _, aggregated = self.aggregate_project_data(project_id)

        clean_aggregated = self._build_clean_aggregated(aggregated)
        mapping = self.storage.get_mapping(project_id)
        self.storage.write_sml_template(project_id)
        updated_metadata = self.storage.get_project(project_id)
        questions = self.storage.get_questions(project_id)
        from source.services.sml_template import build_sml_templates

        return {
            **updated_metadata.model_dump(),
            "Extractions": clean_aggregated,
            "Mappings": mapping.Mappings,
            "SmlTemplate": build_sml_templates(project_id, self.storage),
            "Questions": questions,
        }

    def reanalyze_project_workflow(self, project_id: int) -> dict:
        metadata = self.storage.get_project(project_id)
        batch_path = self.storage.spec_json_path(project_id, "project_batch")
        if batch_path.exists():
            batch_path.unlink()

        for doc in metadata.Documents:
            doc.Status = "uploaded"
        
        self.storage._write_metadata(metadata)
        
        _, aggregated = self.aggregate_project_data(project_id, auto_analyze=True)
        self.storage.save_spec_json(batch_path, aggregated)
        
        clean_aggregated = self._build_clean_aggregated(aggregated)
        mapping = self.storage.get_mapping(project_id)
        updated_metadata = self.storage.get_project(project_id)
        questions = self.storage.get_questions(project_id)
        from source.services.sml_template import build_sml_templates

        return {
            **updated_metadata.model_dump(),
            "Extractions": clean_aggregated,
            "Mappings": mapping.Mappings,
            "SmlTemplate": build_sml_templates(project_id, self.storage),
            "Questions": questions,
        }

    def ask_project_workflow(self, project_id: int, request_question: str, request_document_category: str) -> dict:
        self.storage.get_project(project_id)
        requested_category = (request_document_category or "").strip().lower()

        if requested_category in ("", "all"):
            all_paths = self.storage.all_vectorstore_paths(project_id)
            if not all_paths:
                from fastapi import HTTPException
                raise HTTPException(404, "No indexed content in this project yet")

            all_chunks = []
            for slug, store_path in all_paths.items():
                try:
                    vs = VectorStoreManager(store_path)
                    hits = vs.search_with_filters(
                        request_question, {"project_id": project_id}, k=4
                    )
                    for h in hits:
                        if "document_category" not in h.metadata:
                            h.metadata["document_category"] = slug
                    all_chunks.extend(hits)
                except Exception as exc:
                    logger.warning("Search failed for store '%s': %s", slug, exc)

            if not all_chunks:
                from fastapi import HTTPException
                raise HTTPException(404, "No indexed content in this project yet")

            seen = set()
            unique_chunks = []
            for chunk in all_chunks:
                key = (
                    chunk.metadata.get("document_id"),
                    chunk.metadata.get("chunk_id"),
                    chunk.page_content[:100],
                )
                if key not in seen:
                    seen.add(key)
                    unique_chunks.append(chunk)

            chunks = unique_chunks[:6]

        else:
            if requested_category in ("tables", "variable files"):
                slug = "tables"
            else:
                slug = requested_category.replace(" ", "_").replace("/", "_")

            store_path = self.storage.vectorstore_path_for_category(project_id, slug)
            
            legacy_base = self.storage._project_dir(project_id) / self.storage.VECTORSTORE_DIR
            has_legacy = legacy_base.exists() and (legacy_base / "index.faiss").exists()

            if not store_path.exists() and not has_legacy:
                from fastapi import HTTPException
                if slug == "tables":
                    raise HTTPException(
                        404,
                        f"No extracted tables available for this project. "
                        f"Make sure to extract tables from documents.",
                    )
                else:
                    raise HTTPException(
                        404,
                        f"No indexed content for document category '{request_document_category}' in this project. "
                        f"Upload and analyze a document of that type first.",
                    )

            vs = VectorStoreManager(store_path)
            chunks = vs.search_with_filters(
                request_question, {"project_id": project_id}, k=6
            )

        document_id = chunks[0].metadata.get("document_id") if chunks else "project_batch"

        try:
            spec_json = self.storage.read_spec_json(project_id, document_id)
            spec = EquipmentSpec.model_validate_json(spec_json)
        except Exception:
            spec = EquipmentSpec(ToolID="", ToolType="")

        winning_category = chunks[0].metadata.get("document_category", "") if chunks else requested_category
        if winning_category and winning_category != "all":
            if winning_category == "legacy":
                winning_store_path = self.storage._project_dir(project_id) / self.storage.VECTORSTORE_DIR
            else:
                winning_store_path = self.storage.vectorstore_path_for_category(
                    project_id, winning_category
                )
        else:
            legacy_base = self.storage._project_dir(project_id) / self.storage.VECTORSTORE_DIR
            if legacy_base.exists() and (legacy_base / "index.faiss").exists():
                winning_store_path = legacy_base
            else:
                winning_store_path = self.storage.vectorstore_path_for_category(
                    project_id,
                    requested_category if requested_category not in ("", "all") else "gem_manual",
                )

        qa_store = VectorStoreManager(winning_store_path)
        
        filters = {"project_id": project_id}
        if chunks:
            filters["document_id"] = document_id

        qa_service = self._container.create_qa_service(
            qa_store,
            vector_filters=filters,
        )
        answer_text, source, context_chunks, citations = qa_service.answer(
            query=request_question, 
            spec=spec,
            project_id=project_id,
            document_id=document_id,
            storage_service=self.storage
        )

        return {
            "ProjectID": project_id,
            "DocumentID": document_id,
            "DocumentCategory": winning_category,
            "Answer": answer_text,
            "Source": source,
            "Context": context_chunks,
            "Citations": citations
        }

    def _build_clean_aggregated(self, aggregated: EquipmentSpec) -> AggregatedSpec:
        return AggregatedSpec(
            StatusVariables=[
                {"SVID": v.SVID, "Name": v.Name, "Description": v.Description or "", "DataType": v.DataType, "AccessType": v.AccessType}
                for v in aggregated.StatusVariables
            ],
            DataVariables=[
                {"DvID": v.DvID, "Name": v.Name, "Unit": v.Unit or "", "ValueType": v.ValueType}
                for v in aggregated.DataVariables
            ],
            Events=[
                {
                    "CEID": e.CEID, 
                    "EventName": e.EventName, 
                    "Description": e.Description or "",
                    "LinkedVIDs": e.LinkedVIDs,
                    "LinkedReports": e.LinkedReports if hasattr(e, 'LinkedReports') and e.LinkedReports else []
                }
                for e in aggregated.Events
            ],
            Alarms=[
                {"AlarmID": a.AlarmID, "AlarmName": a.AlarmName, "Severity": a.Severity}
                for a in aggregated.Alarms
            ],
            RemoteCommands=[
                {"RCMD": rc.RCMD, "Description": rc.Description or "", "Parameters": [p.model_dump() for p in rc.Parameters]}
                for rc in aggregated.RemoteCommands
            ],
            States=[
                {"StateID": st.StateID, "Name": st.Name, "Description": st.Description or ""}
                for st in aggregated.States
            ],
            StateTransitions=[
                {"FromState": tr.FromState, "ToState": tr.ToState, "TriggerEvent": tr.TriggerEvent or "", "TriggerCommand": tr.TriggerCommand or "", "Manual": tr.Manual}
                for tr in aggregated.StateTransitions
            ],
            Reports=[
                {"RPTID": r.RPTID, "Name": r.Name, "LinkedVIDs": r.LinkedVIDs, "Reasoning": r.Reasoning or "", "Type": r.Type, "Confidence": r.Confidence}
                for r in aggregated.Reports
            ],
        )

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

        # Auto-generate ToolSpecificTesting script
        try:
            self._container.sml_generation_service.generate_scripts(project_id, spec=aggregated)
            logger.info(f"Successfully generated ToolSpecificTesting script for project {project_id}")
        except Exception as e:
            logger.error(f"Failed to auto-generate ToolSpecificTesting script for project {project_id}: {e}")

        return aggregated

    def generate_project_pdf(self, project_id: int, spec: EquipmentSpec) -> None:
        """Helper to generate the PDF report for a given spec."""
        try:
            metadata = self.storage.get_project(project_id)
            from source.services.report_generator import ReportGenerator
            report_gen = ReportGenerator()
            report_dir = self.storage._project_dir(project_id) / "SummaryReport"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "Summary_Report.pdf"
            report_gen.generate_report(spec, report_path, project_metadata=metadata)
            logger.info(f"Successfully generated Project Summary Report for project {project_id}")
        except Exception as e:
            logger.error("Failed to generate Project Summary Report: %s", e)

    def analyze_project_workflow(self, project_id: int) -> Any:
        """
        Orchestrates the project analysis workflow, optionally triggering aggregation
        if pending documents exist, and building the final extraction response.
        """
        metadata = self.storage.get_project(project_id)
        has_pending = any(doc.Status == "uploaded" for doc in metadata.Documents)

        if has_pending:
            metadata, aggregated = self.aggregate_project_data(project_id, auto_analyze=True)
            self.storage.save_spec_json(self.storage.spec_json_path(project_id, "project_batch"), aggregated)
            self._container.document_service.generate_predefined_questions(project_id, aggregated)
            return self._container.document_service._build_extraction_response(
                project_id, "project_batch", aggregated
            )
        else:
            try:
                spec_json = self.storage.read_spec_json(project_id, "project_batch")
                spec_obj = EquipmentSpec.model_validate_json(spec_json)
                questions = self.storage.get_questions(project_id)
                if not questions:
                    self._container.document_service.generate_predefined_questions(project_id, spec_obj)
                
                # Generate the PDF to ensure it is up to date with the latest json
                self.generate_project_pdf(project_id, spec_obj)

                return self._container.document_service._build_extraction_response(
                    project_id, "project_batch", spec_obj
                )
            except Exception:
                metadata, aggregated = self.aggregate_project_data(project_id, auto_analyze=True)
                self.storage.save_spec_json(self.storage.spec_json_path(project_id, "project_batch"), aggregated)
                self._container.document_service.generate_predefined_questions(project_id, aggregated)
                return self._container.document_service._build_extraction_response(
                    project_id, "project_batch", aggregated
                )

    def update_code_workflow(self, project_id: int, category: str, source_code: str) -> dict:
        self.storage.save_project_code(project_id, category, source_code)
        return {
            "ProjectID": project_id,
            "Category": category,
            "Status": "success",
            "Message": f"Code updated for {category}"
        }

    def update_result_workflow(self, project_id: int, category: str, result: str) -> dict:
        return {
            "ProjectID": project_id,
            "Category": category,
            "Status": "success",
            "Result": result
        }

    def update_extraction_workflow(self, project_id: int, request: dict) -> dict:
        from source.schemas.project import UpdateExtractionRequest
        from source.schemas.secsgem import EquipmentSpec, StatusVariable, DataVariable, Event, Alarm, RemoteCommand, State, StateTransition
        from source.schemas.report import ReportDefinition
        from pydantic import ValidationError
        from fastapi import HTTPException
        
        try:
            validated_req = UpdateExtractionRequest(**request)
        except ValidationError as ve:
            raise HTTPException(422, f"Payload validation failed: {ve}")
        
        self.storage.increment_project_version(project_id)
        json_path = self.storage.spec_json_path(project_id, "project_batch")
        
        try:
            spec_json = self.storage.read_spec_json(project_id, "project_batch")
            spec_obj = EquipmentSpec.model_validate_json(spec_json)
        except Exception:
            spec_obj = EquipmentSpec(ToolID="", ToolType="")
            
        try:
            spec_obj.StatusVariables = [
                StatusVariable(
                    SVID=sv.SVID, Name=sv.Name, Description=sv.Description,
                    DataType=sv.DataType, AccessType=sv.AccessType,
                    Value=sv.Value, Confidence=sv.Confidence
                ) for sv in validated_req.StatusVariables
            ]
            
            spec_obj.DataVariables = [
                DataVariable(
                    DvID=dv.DvID, Name=dv.Name, Unit=dv.Unit, ValueType=dv.ValueType
                ) for dv in validated_req.DataVariables
            ]
            
            spec_obj.Events = [
                Event(
                    CEID=e.CEID, Name=e.EventName, Description=e.Description,
                    LinkedVIDs=e.LinkedVIDs, LinkedReports=e.LinkedReports,
                    Confidence=e.Confidence
                ) for e in validated_req.Events
            ]
            
            spec_obj.Alarms = [
                Alarm(
                    AlarmID=a.AlarmID, Name=a.AlarmName, Severity=a.Severity,
                    LinkedVID=a.LinkedVID, Description=a.Description,
                    Confidence=a.Confidence
                ) for a in validated_req.Alarms
            ]
            
            spec_obj.RemoteCommands = [
                RemoteCommand(
                    RCMD=rc.RCMD, Description=rc.Description, Parameters=rc.Parameters,
                    Confidence=rc.Confidence
                ) for rc in validated_req.RemoteCommands
            ]
            
            spec_obj.States = [State(**s) for s in validated_req.States]
            spec_obj.StateTransitions = [StateTransition(**st) for st in validated_req.StateTransitions]
            spec_obj.Reports = [ReportDefinition(**r) for r in validated_req.Reports]
        except ValidationError as ve:
            raise HTTPException(422, f"Payload mapping failed: {ve}")
        
        self.storage.save_spec_json(json_path, spec_obj)
        self.generate_project_pdf(project_id, spec_obj)
        
        try:
            self._container.sml_generation_service.generate_scripts(project_id, spec=spec_obj)
        except Exception as e:
            logger.error("Failed to auto-generate ToolSpecificTesting script on extraction update: %s", e)
        
        return {"Status": "success", "Message": "Extraction updated successfully"}

    def generate_reports_workflow(self, project_id: int, request: dict) -> dict:
        from source.schemas.secsgem import EquipmentSpec
        self.storage.increment_project_version(project_id)
        json_path = self.storage.spec_json_path(project_id, "project_batch")
        try:
            spec_json = self.storage.read_spec_json(project_id, "project_batch")
            spec_obj = EquipmentSpec.model_validate_json(spec_json)
        except Exception:
            _, spec_obj = self.aggregate_project_data(project_id)
        
        ceids = request.get("ceids", [])
        if ceids:
            target_events = [e for e in spec_obj.Events if e.CEID in ceids]
            original_events = spec_obj.Events
            spec_obj.Events = target_events
            
            new_reports = self._container.report_service.generate_synthetic_reports(spec_obj)
            
            spec_obj.Events = original_events
            
            new_rptids = {r.RPTID for r in new_reports}
            kept_reports = [r for r in spec_obj.Reports if r.RPTID not in new_rptids]
            
            spec_obj.Reports = kept_reports + new_reports
        else:
            reports = self._container.report_service.generate_synthetic_reports(spec_obj)
            spec_obj.Reports = reports
            
        for event in spec_obj.Events:
            if not event.LinkedVIDs:
                event.LinkedReports = []
                continue
            
            uncovered = set(event.LinkedVIDs)
            chosen_rptids = set()
            
            while uncovered:
                best_report = None
                best_cover_count = 0
                best_extra_count = float('inf')
                
                for report in spec_obj.Reports:
                    if report.RPTID in chosen_rptids:
                        continue
                        
                    rpt_vids = set(report.LinkedVIDs)
                    covered = uncovered.intersection(rpt_vids)
                    extra = rpt_vids - set(event.LinkedVIDs)
                    
                    cover_count = len(covered)
                    extra_count = len(extra)
                    
                    if cover_count > best_cover_count:
                        best_cover_count = cover_count
                        best_extra_count = extra_count
                        best_report = report
                    elif cover_count == best_cover_count and cover_count > 0:
                        if extra_count < best_extra_count:
                            best_extra_count = extra_count
                            best_report = report
                            
                if best_report is None:
                    break
                    
                chosen_rptids.add(best_report.RPTID)
                uncovered -= set(best_report.LinkedVIDs)
                
            event.LinkedReports = sorted(list(chosen_rptids))
            
        self.storage.save_spec_json(json_path, spec_obj)
        self.generate_project_pdf(project_id, spec_obj)
        
        try:
            self._container.sml_generation_service.generate_scripts(project_id, spec=spec_obj)
        except Exception as e:
            logger.error("Failed to auto-generate ToolSpecificTesting script after generating reports: %s", e)
        
        return self._container.document_service._build_extraction_response(
            project_id, "project_batch", spec_obj
        )

    def update_reports_workflow(self, project_id: int, request: dict) -> dict:
        from source.schemas.secsgem import EquipmentSpec
        from source.schemas.report import ReportDefinition
        
        reports_data = request.get("Reports", [])
        reports = [ReportDefinition(**r) for r in reports_data]
        
        self.storage.increment_project_version(project_id)
        json_path = self.storage.spec_json_path(project_id, "project_batch")
        try:
            spec_json = self.storage.read_spec_json(project_id, "project_batch")
            spec_obj = EquipmentSpec.model_validate_json(spec_json)
        except Exception:
            _, spec_obj = self.aggregate_project_data(project_id)
        
        spec_obj.Reports = reports
        self.storage.save_spec_json(json_path, spec_obj)
        
        try:
            self._container.sml_generation_service.generate_scripts(project_id, spec=spec_obj)
        except Exception as e:
            logger.error("Failed to auto-generate ToolSpecificTesting script on updating reports: %s", e)
        
        return self._container.document_service._build_extraction_response(
            project_id, "project_batch", spec_obj
        )

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
