import logging

from fastapi import FastAPI

from app.db import Base, SessionLocal, engine
from app.routers.equipment_routes import router as equipment_router
from app.routers.mapping_routes import router as mapping_router
from app.routers.project_routes import router as project_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="EAP SECS/GEM Extractor")
app.include_router(equipment_router)
app.include_router(mapping_router)
app.include_router(project_router)


@app.on_event("startup")
def startup_reindex() -> None:
    from pathlib import Path
    from app.config import settings
    from app.models.models import EquipmentSpecRow
    from app.managers.service_container import container

    vector_dir = Path(settings.VECTORSTORE_ROOT)
    index_missing = not vector_dir.exists() or not any(vector_dir.iterdir())

    if not index_missing:
        logger.info("FAISS index found at %s — skipping re-index.", vector_dir)
        return

    db = SessionLocal()
    try:
        rows: list[EquipmentSpecRow] = db.query(EquipmentSpecRow).all()
        if not rows:
            logger.info("No specs in DB — nothing to re-index.")
            return

        logger.warning(
            "vectorstores/ is missing or empty.  Re-indexing %d document(s) from DB …",
            len(rows),
        )
        for row in rows:
            if not row.raw_text:
                logger.warning("Skipping spec id=%d (%s) — raw_text is empty.", row.id, row.tool_id)
                continue
            container.vector_store.add_document(
                row.raw_text,
                metadata={"tool_id": row.tool_id, "spec_id": row.id},
            )
            logger.info("  Re-indexed spec id=%d  tool_id=%s", row.id, row.tool_id)

        logger.info("Re-index complete.")
    finally:
        db.close()


@app.get("/health")
def health():
    return {"status": "ok"}
