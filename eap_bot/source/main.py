import logging

from fastapi import FastAPI

from source.routers.equipment_routes import EquipmentAPI
from source.routers.mapping_routes import MappingAPI
from source.routers.project_routes import ProjectAPI
from source.routers.codegen_routes import CodeGenAPI
from source.services.storage_service import StorageService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="EAP SECS/GEM Extractor")

project_api = ProjectAPI()
equipment_api = EquipmentAPI()
mapping_api = MappingAPI()
codegen_api = CodeGenAPI()

app.include_router(project_api.router)
app.include_router(equipment_api.router)
#app.include_router(mapping_api.router)
#app.include_router(codegen_api.router)


@app.on_event("startup")
def validate_storage_root() -> None:
    storage = StorageService()
    logger.info("Using EAP_STORAGE_ROOT=%s", storage.root)


@app.get("/health")
def health():
    return {"status": "ok"}
