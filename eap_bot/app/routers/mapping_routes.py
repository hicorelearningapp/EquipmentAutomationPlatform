from fastapi import APIRouter


class MappingAPI:
    def __init__(self):
        self.router = APIRouter(prefix="/mapping", tags=["mapping"])
        self.register_routes()

    def register_routes(self):
        self.router.get("/status")(self.mapping_status)

    def mapping_status(self):
        return {
            "status": "disabled",
            "message": (
                "Mapping schemas and service code are retained, but persistence and "
                "approval APIs need to be rebuilt on the filesystem storage model."
            ),
        }
