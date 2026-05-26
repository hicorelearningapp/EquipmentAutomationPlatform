from source.schemas.project import ProjectDetailsResponse, SystemSummaryResponse
from source.schemas.secsgem import EquipmentSpec
from source.services.storage_service import StorageService


class ProjectDetailsService:
    def __init__(self, storage: StorageService):
        self.storage = storage

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
            ConnectedToolCount=len(metadata.ConnectedTools) if hasattr(metadata, "ConnectedTools") and metadata.ConnectedTools else 0,
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
        
        for project in projects:
            tool_char_dir = self.storage._project_dir(project.ProjectID) / self.storage.TOOL_CHAR_DIR
            if tool_char_dir.is_dir():
                total_sml += len([f for f in tool_char_dir.iterdir() if f.is_file()])
            
            try:
                full_meta = self.storage.get_project(project.ProjectID)
                if hasattr(full_meta, "ConnectedTools") and full_meta.ConnectedTools:
                    total_tools += len(full_meta.ConnectedTools)
            except Exception:
                pass
                
        return SystemSummaryResponse(
            TotalProjects=len(projects),
            TotalSmlScripts=total_sml,
            TotalConnectedTools=total_tools,
        )
