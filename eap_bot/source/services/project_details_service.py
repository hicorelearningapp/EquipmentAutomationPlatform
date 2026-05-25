from source.schemas.project import ProjectDetailsResponse
from source.schemas.secsgem import EquipmentSpec
from source.services.storage_service import StorageService


class ProjectDetailsService:
    def __init__(self, storage: StorageService):
        self.storage = storage

    def get_project_details(self, project_id: int) -> ProjectDetailsResponse:
        metadata = self.storage.get_project(project_id)

        documents = metadata.Documents or []

        number_of_documents = len(documents)

        number_of_xml_files = len([
            d for d in documents
            if d.FileName.lower().endswith(".xml")
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
            CreatedAt=metadata.CreatedAt,
            NumberOfDocuments=number_of_documents,
            NumberOfSVs=total_svs,
            NumberOfDVs=total_dvs,
            NumberOfRemoteCommands=total_rcmds,
            NumberOfXMLFiles=number_of_xml_files,
            NumberOfReports=total_reports,
            NumberOfAlarms=total_alarms,
            NumberOfEvents=total_events,
        )
