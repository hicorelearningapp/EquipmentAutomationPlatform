import json
import logging
import shutil
from pathlib import Path
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Same path resolution as project_service.py and mes_family_seed.py
MES_MAP_DIR: Path = Path(__file__).resolve().parent.parent.parent / "MESMapTemplates"
FAMILIES_FILE: Path = MES_MAP_DIR / "families.json"

class UpdateFamiliesRequest(BaseModel):
    action: str           # "add" | "update" | "delete"
    Family: str
    DefaultProtocol: str = ""
    RequiresAck: bool = True
    Description: str = ""

def _load_families() -> list:
    if not FAMILIES_FILE.exists():
        return []
    try:
        with open(FAMILIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load families: %s", e)
        raise HTTPException(500, f"Error reading families database: {e}")

def _save_families(families: list) -> None:
    try:
        MES_MAP_DIR.mkdir(parents=True, exist_ok=True)
        with open(FAMILIES_FILE, "w", encoding="utf-8") as f:
            json.dump(families, f, indent=2)
    except Exception as e:
        logger.error("Failed to save families: %s", e)
        raise HTTPException(500, f"Error writing to families database: {e}")

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

    def get_mes_families(self):
        return _load_families()

    def update_mes_families(self, body: UpdateFamiliesRequest):
        families = _load_families()
        action = body.action.lower().strip()

        if action == "add":
            for fam in families:
                if fam.get("Family", "").lower() == body.Family.lower():
                    raise HTTPException(409, f"MES Family '{body.Family}' already exists")
            
            new_fam = {
                "Family": body.Family,
                "DefaultProtocol": body.DefaultProtocol,
                "RequiresAck": body.RequiresAck,
                "Description": body.Description
            }
            families.append(new_fam)
            _save_families(families)

            family_dir = MES_MAP_DIR / body.Family
            try:
                family_dir.mkdir(parents=True, exist_ok=True)
                template_file = family_dir / "STANDARD_EVENT_MODEL.json"
                if not template_file.exists():
                    skeleton = {
                        "Events": [],
                        "Alarms": [],
                        "Variables": [],
                        "Payloads": [],
                        "Transactions": [],
                        "ValidationRules": [],
                        "AutoMapping": {},
                        "Logging": {}
                    }
                    with open(template_file, "w", encoding="utf-8") as f:
                        json.dump(skeleton, f, indent=2)
            except Exception as e:
                logger.error("Failed to create directory structure for new family %s: %s", body.Family, e)
                raise HTTPException(500, f"Error creating family directory: {e}")

            return {
                "Status": "success",
                "Message": f"MES Family '{body.Family}' added successfully",
                "Family": new_fam
            }

        elif action == "update":
            found = False
            for fam in families:
                if fam.get("Family", "").lower() == body.Family.lower():
                    fam["DefaultProtocol"] = body.DefaultProtocol
                    fam["RequiresAck"] = body.RequiresAck
                    fam["Description"] = body.Description
                    found = True
                    break
            
            if not found:
                raise HTTPException(404, f"MES Family '{body.Family}' not found")
            
            _save_families(families)
            return {
                "Status": "success",
                "Message": f"MES Family '{body.Family}' updated successfully"
            }

        elif action == "delete":
            target_fam = None
            for fam in families:
                if fam.get("Family", "").lower() == body.Family.lower():
                    target_fam = fam
                    break
            
            if not target_fam:
                raise HTTPException(404, f"MES Family '{body.Family}' not found")
            
            families.remove(target_fam)
            _save_families(families)

            family_dir = MES_MAP_DIR / target_fam["Family"]
            if family_dir.exists() and family_dir.is_dir():
                try:
                    shutil.rmtree(family_dir)
                except Exception as e:
                    logger.error("Failed to delete directory for family %s: %s", target_fam["Family"], e)
                    raise HTTPException(500, f"Failed to delete family directory: {e}")

            return {
                "Status": "success",
                "Message": f"MES Family '{target_fam['Family']}' deleted successfully"
            }

        else:
            raise HTTPException(400, f"Invalid action '{body.action}'. Allowed actions: add, update, delete")

    def get_mes_templates(self, mes_family: str):
        family_dir = (MES_MAP_DIR / mes_family).resolve()
        if not family_dir.exists() or not family_dir.is_dir() or MES_MAP_DIR not in family_dir.parents:
            families = _load_families()
            found = any(f.get("Family", "").lower() == mes_family.lower() for f in families)
            if not found:
                raise HTTPException(404, f"MES Family '{mes_family}' not found")
            return []

        try:
            files = [f.name for f in family_dir.glob("*.json")]
            return files
        except Exception as e:
            logger.error("Failed to list templates for family %s: %s", mes_family, e)
            raise HTTPException(500, f"Error listing templates: {e}")

    def get_mes_template_info(self, mes_family: str, template: str):
        family_dir = (MES_MAP_DIR / mes_family).resolve()
        if not family_dir.exists() or not family_dir.is_dir() or MES_MAP_DIR not in family_dir.parents:
            raise HTTPException(404, f"MES Family '{mes_family}' not found")

        if not template.endswith(".json"):
            template = f"{template}.json"

        template_path = (family_dir / template).resolve()
        if not template_path.exists() or family_dir not in template_path.parents:
            raise HTTPException(404, f"Template '{template}' not found in family '{mes_family}'")

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to read template %s from family %s: %s", template, mes_family, e)
            raise HTTPException(500, f"Error reading template info: {e}")

    async def add_mes_template_info(self, mes_family: str, file: UploadFile = File(...)):
        family_dir = (MES_MAP_DIR / mes_family).resolve()
        if not family_dir.exists() or not family_dir.is_dir() or MES_MAP_DIR not in family_dir.parents:
            raise HTTPException(404, f"MES Family '{mes_family}' not found")

        if not file.filename or not file.filename.lower().endswith(".json"):
            raise HTTPException(400, "Only .json files are accepted for templates")

        template_path = (family_dir / file.filename).resolve()
        if template_path.exists():
            raise HTTPException(409, f"Template '{file.filename}' already exists in family '{mes_family}'")

        if family_dir not in template_path.parents:
            raise HTTPException(400, "Invalid template filename")

        try:
            contents = await file.read()
            try:
                json_data = json.loads(contents.decode("utf-8"))
            except Exception as je:
                raise HTTPException(400, f"Invalid JSON payload: {je}")

            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2)

            return {
                "Status": "success",
                "Message": f"Template '{file.filename}' added successfully to family '{mes_family}'"
            }
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error("Failed to upload template: %s", e)
            raise HTTPException(500, f"Error uploading template: {e}")

mes_family_api = MesFamilyAPI()
