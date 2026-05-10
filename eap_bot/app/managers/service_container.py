import logging

from app.services.equipment_extractor import EquipmentExtractor
from app.services.mapping_service import MappingService
from app.services.qa_service import QAService
from app.utils.embedder import VectorStoreManager
from app.utils.llm_factory import LLMFactory, LLMStrategy
from app.utils.pdf_reader import DocumentParser, DocumentParserFactory
from app.validators.spec_validator import SpecValidator

logger = logging.getLogger(__name__)


class ServiceContainer:
    def __init__(self) -> None:
        logger.info("ServiceContainer: initialising services ...")

        self.llm_strategy: LLMStrategy = LLMFactory.create_strategy()

        self.parser: DocumentParser = DocumentParserFactory.create()
        self.validator: SpecValidator = SpecValidator()
        self.extractor: EquipmentExtractor = EquipmentExtractor(
            llm_strategy=self.llm_strategy
        )
        self.mapping_service: MappingService = MappingService(
            llm_strategy=self.llm_strategy
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
