import json
from pathlib import Path

def migrate_file(filepath: Path):
    if not filepath.exists():
        print(f"Skipping {filepath}, does not exist.")
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        modified = False
        
        # Modify Events
        for event in data.get("Events", []):
            if "ReportID" in event:
                event.pop("ReportID")
                modified = True
            if "Report" in event:
                event.pop("Report")
                modified = True
                
        # Modify Reports
        for report in data.get("Reports", []):
            if "Items" in report:
                report["LinkedVIDs"] = report.pop("Items")
                modified = True
            if "Type" not in report:
                report["Type"] = "Generated"
                modified = True
                
        if modified:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            print(f"Migrated: {filepath}")
        else:
            print(f"No changes needed: {filepath}")

    except Exception as e:
        print(f"Failed to migrate {filepath}: {e}")

if __name__ == "__main__":
    base_dir = Path(__file__).parent
    
    # Root file
    migrate_file(base_dir / "project_batch_13_server.json")
    
    # Project files
    projects_dir = base_dir / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir() and project_dir.name.isdigit():
                json_dir = project_dir / "ExtractedJson"
                if json_dir.exists():
                    for json_file in json_dir.glob("*.json"):
                        migrate_file(json_file)
