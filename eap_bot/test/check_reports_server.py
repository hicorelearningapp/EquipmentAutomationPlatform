import json
from pathlib import Path

for p in Path("/root/eap_bot/projects").rglob("*.json"):
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        reports = data.get("Reports", [])
        if len(reports) > 0:
            missing_type = 0
            for r in reports:
                if "Type" not in r:
                    missing_type += 1
            print(f"{p}: {len(reports)} reports, {missing_type} missing Type")
    except Exception as e:
        pass
