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
        logger.info("ServiceContainer: initialising services …")

        strategy: LLMStrategy = LLMFactory.create_strategy()

        self.parser: DocumentParser = DocumentParserFactory.create()
        self.validator: SpecValidator = SpecValidator()
        self.vector_store: VectorStoreManager = VectorStoreManager()
        self.extractor: EquipmentExtractor = EquipmentExtractor(llm_strategy=strategy)
        self.qa_service: QAService = QAService(llm_strategy=strategy, vector_store=self.vector_store)
        self.mapping_service: MappingService = MappingService(llm_strategy=strategy)

        logger.info("ServiceContainer: all services ready.")

container = ServiceContainer()
