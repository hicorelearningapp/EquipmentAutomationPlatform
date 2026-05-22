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

class MesFamilySchema(BaseModel):
    FamilyID: int | None = None
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

def _resolve_canonical_family(mes_family: str) -> str:
    families = _load_families()
    for f in families:
        if f.get("Family", "").lower() == mes_family.lower():
            return f["Family"]
    raise HTTPException(404, f"MES Family '{mes_family}' not found")

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
        return _load_families()

    def update_mes_families(self, body: list[MesFamilySchema]):
        # 1. Validation
        seen_names = set()
        seen_ids = set()
        for item in body:
            name_lower = item.Family.strip().lower()
            if name_lower in seen_names:
                raise HTTPException(400, f"Duplicate family name '{item.Family}' is not allowed")
            seen_names.add(name_lower)
            
            if item.FamilyID is not None:
                if item.FamilyID in seen_ids:
                    raise HTTPException(400, f"Duplicate FamilyID '{item.FamilyID}' is not allowed")
                seen_ids.add(item.FamilyID)

        # Load old families
        old_families = _load_families()
        old_families_by_id = {f["FamilyID"]: f for f in old_families if f.get("FamilyID") is not None}
        old_families_by_name = {f["Family"].strip().lower(): f for f in old_families}

        new_families_list = []
        used_old_ids = set()

        # Step 2: Match incoming families to their old equivalents
        for item in body:
            matched_old = None
            if item.FamilyID is not None and item.FamilyID in old_families_by_id:
                matched_old = old_families_by_id[item.FamilyID]
            else:
                # Fallback to name match
                name_key = item.Family.strip().lower()
                if name_key in old_families_by_name:
                    matched_old = old_families_by_name[name_key]

            if matched_old:
                assigned_id = matched_old["FamilyID"]
                used_old_ids.add(assigned_id)

                # Rename directory if name changed
                old_name = matched_old["Family"]
                if old_name.strip() != item.Family.strip():
                    old_dir = MES_MAP_DIR / old_name
                    new_dir = MES_MAP_DIR / item.Family
                    try:
                        if old_dir.exists() and old_dir.is_dir():
                            if old_dir.resolve() != new_dir.resolve():
                                old_dir.rename(new_dir)
                        else:
                            new_dir.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        logger.error("Failed to rename family directory from %s to %s: %s", old_name, item.Family, e)
                        raise HTTPException(500, f"Error renaming family directory: {e}")
            else:
                assigned_id = None

            new_families_list.append({
                "FamilyID": assigned_id,
                "Family": item.Family,
                "DefaultProtocol": item.DefaultProtocol,
                "RequiresAck": item.RequiresAck,
                "Description": item.Description
            })

        # Step 3: Allocate auto-increment IDs for new families
        max_id = max([f.get("FamilyID", 0) for f in old_families] + [6])
        next_id = max_id + 1

        for item in new_families_list:
            if item["FamilyID"] is None:
                item["FamilyID"] = next_id
                next_id += 1

                # Create directory and seed STANDARD_EVENT_MODEL.json
                family_dir = MES_MAP_DIR / item["Family"]
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
                    logger.error("Failed to create directory structure for new family %s: %s", item["Family"], e)
                    raise HTTPException(500, f"Error creating family directory: {e}")

        # Step 4: Process deletions (old families missing in the new list)
        deleted_families = [f for f in old_families if f.get("FamilyID") not in used_old_ids]
        for del_fam in deleted_families:
            del_name = del_fam["Family"]
            del_dir = MES_MAP_DIR / del_name
            if del_dir.exists() and del_dir.is_dir():
                try:
                    shutil.rmtree(del_dir)
                except Exception as e:
                    logger.error("Failed to delete directory for family %s: %s", del_name, e)
                    raise HTTPException(500, f"Failed to delete family directory: {e}")

        # Step 5: Save updated families list to families.json
        _save_families(new_families_list)

        return {
            "Status": "success",
            "Message": "MES families updated successfully",
            "Families": new_families_list
        }


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
        canonical_name = _resolve_canonical_family(mes_family)
        family_dir = (MES_MAP_DIR / canonical_name).resolve()
        if not family_dir.exists() or not family_dir.is_dir() or MES_MAP_DIR not in family_dir.parents:
            raise HTTPException(404, f"MES Family '{canonical_name}' not found")

        if not file.filename or not file.filename.lower().endswith(".json"):
            raise HTTPException(400, "Only .json files are accepted for templates")

        template_path = (family_dir / file.filename).resolve()
        if template_path.exists():
            raise HTTPException(409, f"Template '{file.filename}' already exists in family '{canonical_name}'")

        if family_dir not in template_path.parents:
            raise HTTPException(400, "Invalid template filename")

        try:
            contents = await file.read()
            try:
                json_data = json.loads(contents.decode("utf-8"))
            except Exception as je:
                raise HTTPException(400, f"Invalid JSON payload: {je}")

            # Validate MESFamily if present
            if "MESFamily" in json_data:
                if json_data["MESFamily"].lower() != canonical_name.lower():
                    raise HTTPException(
                        422,
                        f"MESFamily '{json_data['MESFamily']}' in the template does not match the target family '{canonical_name}'"
                    )

            # Auto-inject/overwrite TemplateName
            json_data["TemplateName"] = Path(file.filename).stem

            # Auto-inject MESFamily
            json_data["MESFamily"] = canonical_name

            # Version handling
            if "Version" not in json_data:
                json_data["Version"] = "1.0"

            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2)

            return {
                "Status": "success",
                "Message": f"Template '{file.filename}' added successfully to family '{canonical_name}'"
            }
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error("Failed to upload template: %s", e)
            raise HTTPException(500, f"Error uploading template: {e}")

    async def update_mes_template_info(self, mes_family: str, template: str, file: UploadFile = File(...)):
        canonical_name = _resolve_canonical_family(mes_family)
        family_dir = (MES_MAP_DIR / canonical_name).resolve()
        if not family_dir.exists() or not family_dir.is_dir() or MES_MAP_DIR not in family_dir.parents:
            raise HTTPException(404, f"MES Family '{canonical_name}' not found")

        if not template.endswith(".json"):
            template = f"{template}.json"

        template_path = (family_dir / template).resolve()
        if not template_path.exists() or family_dir not in template_path.parents:
            raise HTTPException(404, f"Template '{template}' not found in family '{canonical_name}'")

        if not file.filename or not file.filename.lower().endswith(".json"):
            raise HTTPException(400, "Only .json files are accepted for templates")

        try:
            contents = await file.read()
            try:
                json_data = json.loads(contents.decode("utf-8"))
            except Exception as je:
                raise HTTPException(400, f"Invalid JSON payload: {je}")

            # Validate MESFamily if present
            if "MESFamily" in json_data:
                if json_data["MESFamily"].lower() != canonical_name.lower():
                    raise HTTPException(
                        422,
                        f"MESFamily '{json_data['MESFamily']}' in the template does not match the target family '{canonical_name}'"
                    )

            # Read current on-disk version of the template
            existing_version = "1.0"
            try:
                with open(template_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    existing_version = existing_data.get("Version", "1.0")
            except Exception as re:
                logger.warning("Failed to read existing version from %s, defaulting to 1.0: %s", template_path, re)

            # Version handling
            if "Version" in json_data:
                # User provided version: keep as-is
                pass
            else:
                # Auto-increment +0.1
                try:
                    current_float = float(existing_version)
                except ValueError:
                    current_float = 1.0
                new_float = round(current_float + 0.1, 1)
                json_data["Version"] = str(new_float)

            # Auto-inject/overwrite TemplateName
            json_data["TemplateName"] = Path(template).stem

            # Auto-inject MESFamily
            json_data["MESFamily"] = canonical_name

            with open(template_path, "w", encoding="utf-8") as f:
                json.dump(json_data, f, indent=2)

            return {
                "Status": "success",
                "Message": f"Template '{template}' updated successfully in family '{canonical_name}'",
                "Version": json_data["Version"]
            }
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error("Failed to update template: %s", e)
            raise HTTPException(500, f"Error updating template: {e}")

mes_family_api = MesFamilyAPI()
