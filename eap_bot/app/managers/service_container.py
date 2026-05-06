import logging

from app.services.equipment_extractor import EquipmentExtractor
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
        self.extractor: EquipmentExtractor = EquipmentExtractor(llm_strategy=strategy)

        logger.info("ServiceContainer: all services ready.")

container = ServiceContainer()
