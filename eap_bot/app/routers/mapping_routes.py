from fastapi import APIRouter

router = APIRouter(prefix="/mapping", tags=["mapping"])


@router.get("/status")
def mapping_status():
    return {
        "status": "disabled",
        "message": (
            "Mapping schemas and service code are retained, but persistence and "
            "approval APIs need to be rebuilt on the filesystem storage model."
        ),
    }
