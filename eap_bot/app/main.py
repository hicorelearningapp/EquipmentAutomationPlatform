import logging

from fastapi import FastAPI

from app.routers.equipment_routes import router as equipment_router
from app.routers.project_routes import router as project_router
from app.services.storage_service import StorageService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="EAP SECS/GEM Extractor")
app.include_router(project_router)
app.include_router(equipment_router)


@app.on_event("startup")
def validate_storage_root() -> None:
    storage = StorageService()
    logger.info("Using EAP_STORAGE_ROOT=%s", storage.root)


@app.get("/health")
def health():
    return {"status": "ok"}
