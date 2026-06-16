import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from source.config import settings
from source.routers.automap_routes import AutoMapAPI
from source.routers.equipment_routes import EquipmentAPI
from source.routers.mapping_routes import MappingAPI
from source.routers.project_routes import ProjectAPI
from source.routers.codegen_routes import CodeGenAPI
from source.routers.tool_characterization_routes import ToolCharacterizationAPI
from source.routers.smart_automation_routes import SmartAutomationAPI
from source.routers.mes_family_routes import mes_family_api
from source.routers.system_routes import SystemAPI
from source.managers.service_container import container
from source.services.mes_family_seed import seed_mes_families

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="EAP SECS/GEM Extractor")
app.mount("/projects", StaticFiles(directory=settings.EAP_STORAGE_ROOT), name="projects")

from fastapi.openapi.utils import get_openapi

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )

    # --- Fix 1: Replace contentMediaType with format: binary ---------------
    # Swagger UI doesn't understand OpenAPI 3.1's contentMediaType for file
    # uploads; swap it for the legacy format: "binary" it expects.
    def fix_binary_fields(d):
        if isinstance(d, dict):
            if d.get("contentMediaType") == "application/octet-stream":
                del d["contentMediaType"]
                d["format"] = "binary"
            for v in d.values():
                fix_binary_fields(v)
        elif isinstance(d, list):
            for item in d:
                fix_binary_fields(item)

    fix_binary_fields(openapi_schema)

    # --- Fix 2: Inline $ref schemas for multipart/form-data ----------------
    # Swagger UI can't detect format: binary inside array items when it has
    # to chase a $ref pointer.  Inline the component schema directly so the
    # file-picker renderer sees the types without indirection.
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    for _path, methods in openapi_schema.get("paths", {}).items():
        for _method, operation in methods.items():
            if not isinstance(operation, dict):
                continue
            mp = (
                operation
                .get("requestBody", {})
                .get("content", {})
                .get("multipart/form-data", {})
            )
            ref = mp.get("schema", {}).get("$ref")
            if ref and ref.startswith("#/components/schemas/"):
                schema_name = ref.rsplit("/", 1)[-1]
                if schema_name in schemas:
                    import copy
                    mp["schema"] = copy.deepcopy(schemas[schema_name])

    app.openapi_schema = openapi_schema
    return openapi_schema

app.openapi = custom_openapi

project_api = ProjectAPI()
equipment_api = EquipmentAPI()
mapping_api = MappingAPI()
automap_api = AutoMapAPI()
codegen_api = CodeGenAPI()
tool_char_api = ToolCharacterizationAPI()
smart_auto_api = SmartAutomationAPI()
system_api = SystemAPI()

app.include_router(project_api.router)
app.include_router(equipment_api.router)
app.include_router(mapping_api.router)
app.include_router(automap_api.router)
app.include_router(mes_family_api.router)
app.include_router(tool_char_api.router)
app.include_router(smart_auto_api.router)
app.include_router(system_api.router)
#app.include_router(codegen_api.router)


@app.on_event("startup")
def validate_storage_root() -> None:
    storage = container.storage
    logger.info("Using EAP_STORAGE_ROOT=%s", storage.root)
    seed_mes_families()


@app.get("/health")
def health():
    return {"status": "ok"}

