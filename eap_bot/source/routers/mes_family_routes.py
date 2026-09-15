import logging
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel
from source.managers.service_container import container

logger = logging.getLogger(__name__)

class MesFamilySchema(BaseModel):
    FamilyID: int | None = None
    Family: str
    DefaultProtocol: str = ""
    RequiresAck: bool = True
    Description: str = ""

class MesFamilyAPI:
    def __init__(self):
        self.router = APIRouter(tags=["MES Families"])
        self.register_routes()

    def register_routes(self):
        self.router.get("/GetMesFamilies")(self.get_mes_families)
        self.router.post("/UpdateMesFamilies")(self.update_mes_families)
        self.router.get("/GetMesTemplates/{mes_family}")(self.get_mes_templates)
        self.router.get("/GetMesTemplateInfo/{mes_family}/{template}")(self.get_mes_template_info)
        self.router.post("/AddMesTemplateInfo/{mes_family}")(self.add_mes_template_info)
        self.router.put("/UpdateMesTemplateInfo/{mes_family}/{template}")(self.update_mes_template_info)

    def get_mes_families(self):
        return container.mes_family_service.get_mes_families()

    def update_mes_families(self, body: list[MesFamilySchema]):
        return container.mes_family_service.update_mes_families(body)

    def get_mes_templates(self, mes_family: str):
        return container.mes_family_service.get_mes_templates(mes_family)

    def get_mes_template_info(self, mes_family: str, template: str):
        return container.mes_family_service.get_mes_template_info(mes_family, template)

    async def add_mes_template_info(self, mes_family: str, file: UploadFile = File(...)):
        contents = await file.read()
        return container.mes_family_service.add_mes_template_info(mes_family, file.filename, contents)

    async def update_mes_template_info(self, mes_family: str, template: str, file: UploadFile = File(...)):
        contents = await file.read()
        return container.mes_family_service.update_mes_template_info(mes_family, template, file.filename, contents)

mes_family_api = MesFamilyAPI()
