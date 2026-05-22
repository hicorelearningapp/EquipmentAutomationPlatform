"""
mes_family_seed.py
==================
Called once at startup (from main.py).
Creates MESMapTemplates/families.json and one seed template per family
if — and only if — those files do not already exist.
"""
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Canonical root (same resolution as project_service.py MESMapTemplates ref) ─
MES_MAP_DIR: Path = Path(__file__).resolve().parent.parent.parent / "MESMapTemplates"
FAMILIES_FILE: Path = MES_MAP_DIR / "families.json"

# ── Default families registry ─────────────────────
DEFAULT_FAMILIES = [
    {
        "FamilyID": 1,
        "Family": "FactoryWorks",
        "DefaultProtocol": "",
        "RequiresAck": True,
        "Description": "FactoryWorks MES"
    },
    {
        "FamilyID": 2,
        "Family": "FAB300",
        "DefaultProtocol": "",
        "RequiresAck": True,
        "Description": "FAB300 MES"
    },
    {
        "FamilyID": 3,
        "Family": "PROMIS",
        "DefaultProtocol": "",
        "RequiresAck": True,
        "Description": "PROMIS MES"
    },
    {
        "FamilyID": 4,
        "Family": "Camstar",
        "DefaultProtocol": "",
        "RequiresAck": True,
        "Description": "Camstar MES"
    },
    {
        "FamilyID": 5,
        "Family": "Critical Manufacturing",
        "DefaultProtocol": "",
        "RequiresAck": True,
        "Description": "Critical Manufacturing MES"
    },
    {
        "FamilyID": 6,
        "Family": "Custom MES",
        "DefaultProtocol": "",
        "RequiresAck": True,
        "Description": "Custom MES"
    }
]

def _seed_template(family_name: str) -> dict:
    """Generates a STANDARD_EVENT_MODEL.json skeleton."""
    return {
        "Events": [],
        "Alarms": [],
        "Variables": [],
        "Payloads": [],
        "Transactions": [],
        "ValidationRules": [],
        "AutoMapping": {},
        "Logging": {}
    }

def seed_mes_families() -> None:
    """Idempotently seed default families and template structures."""
    try:
        # 1. Ensure MES_MAP_DIR exists
        MES_MAP_DIR.mkdir(parents=True, exist_ok=True)

        # 2. Seed families.json if it does not exist
        if not FAMILIES_FILE.exists():
            logger.info("Seeding default MES families to %s", FAMILIES_FILE)
            with open(FAMILIES_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_FAMILIES, f, indent=2)

        # Read families to see what subdirectories to verify/create
        try:
            with open(FAMILIES_FILE, "r", encoding="utf-8") as f:
                families = json.load(f)
        except Exception as e:
            logger.error("Failed to read families registry file: %s", e)
            families = DEFAULT_FAMILIES

        # Auto-migration: assign integer FamilyIDs to any entries missing them
        needs_save = False
        existing_ids = {fam.get("FamilyID") for fam in families if fam.get("FamilyID") is not None}
        next_id = max(existing_ids) + 1 if existing_ids else 1

        for fam in families:
            if fam.get("FamilyID") is None:
                fam["FamilyID"] = next_id
                next_id += 1
                needs_save = True

        if needs_save:
            logger.info("Saving migrated families registry with integer FamilyIDs")
            with open(FAMILIES_FILE, "w", encoding="utf-8") as f:
                json.dump(families, f, indent=2)

        # 3. For each family, ensure directory and STANDARD_EVENT_MODEL.json exist
        for fam_entry in families:
            family_name = fam_entry.get("Family")
            if not family_name:
                continue

            family_dir = MES_MAP_DIR / family_name
            family_dir.mkdir(parents=True, exist_ok=True)

            template_file = family_dir / "STANDARD_EVENT_MODEL.json"
            if not template_file.exists():
                logger.info("Seeding STANDARD_EVENT_MODEL.json for family: %s", family_name)
                skeleton = _seed_template(family_name)
                with open(template_file, "w", encoding="utf-8") as f:
                    json.dump(skeleton, f, indent=2)
            else:
                logger.debug("STANDARD_EVENT_MODEL.json for family: %s already exists, skipping", family_name)

        logger.info("MES family seeding complete.")
    except Exception as e:
        logger.error("Error seeding MES families: %s", e, exc_info=True)

