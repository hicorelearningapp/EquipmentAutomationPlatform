import logging

from fastapi import APIRouter, HTTPException

from source.managers.service_container import container
from source.schemas.automap import AutoMapRequest, AutoMapResponse

logger = logging.getLogger(__name__)


class AutoMapAPI:
    def __init__(self) -> None:
        self.router = APIRouter(tags=["automap"])
        self.router.post("/AutoMap", response_model=AutoMapResponse)(self.run_automap)

    def run_automap(self, body: AutoMapRequest) -> AutoMapResponse:
        try:
            return container.automap_service.run(
                project_id=body.project_id,
                family=body.family,
                template=body.template,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except Exception as exc:
            logger.error("AutoMap failed: %s", exc, exc_info=True)
            raise HTTPException(500, f"AutoMap failed: {exc}") from exc
