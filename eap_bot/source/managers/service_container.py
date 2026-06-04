import logging

from source.services.automap_service import AutoMapService
from source.services.equipment_extractor import EquipmentExtractor
from source.services.mapping_service import MappingService
from source.services.qa_service import QAService
from source.services.report_service import ReportService
from source.services.storage_service import StorageService
from source.services.smart_automation_service import SmartAutomationService
from source.utils.embedder import VectorStoreManager
from source.utils.llm_factory import LLMFactory, LLMStrategy
from source.utils.pdf_reader import DocumentParser, DocumentParserFactory
from source.validators.spec_validator import SpecValidator

logger = logging.getLogger(__name__)


class ServiceContainer:
    def __init__(self) -> None:
        logger.info("ServiceContainer: initialising services ...")

        self.llm_strategy: LLMStrategy = LLMFactory.create_strategy()
        self.storage: StorageService = StorageService()

        self.parser: DocumentParser = DocumentParserFactory.create()
        self.validator: SpecValidator = SpecValidator()
        self.extractor: EquipmentExtractor = EquipmentExtractor(
            llm_strategy=self.llm_strategy
        )
        self.mapping_service: MappingService = MappingService(
            llm_strategy=self.llm_strategy
        )
        self.report_service: ReportService = ReportService(
            llm_strategy=self.llm_strategy
        )
        self.automap_service: AutoMapService = AutoMapService(
            storage=self.storage,
            llm_strategy=self.llm_strategy,
        )
        self.smart_automation_service: SmartAutomationService = SmartAutomationService()

        # Import here to avoid circular imports at module load time
        from source.services.project_service import ProjectService
        from source.services.document_service import DocumentService

        self.project_service: ProjectService = ProjectService(
            storage=self.storage, container=self
        )
        self.document_service: DocumentService = DocumentService(
            storage=self.storage, container=self
        )

        logger.info("ServiceContainer: all services ready.")

    def create_qa_service(
        self,
        vector_store: VectorStoreManager,
        vector_filters: dict | None = None,
    ) -> QAService:
        return QAService(
            llm_strategy=self.llm_strategy,
            vector_store=vector_store,
            vector_filters=vector_filters,
        )


container = ServiceContainer()