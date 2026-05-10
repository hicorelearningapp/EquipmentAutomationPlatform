import os, json
from datetime import datetime

ROOT = '/root/eap_bot/projects'

MAPPING = {
    "id": "ProjectID",
    "project_id": "ProjectID",
    "name": "ProjectName",
    "project_name": "ProjectName",
    "vendor_name": "VendorName",
    "tool": "Tool",
    "project_version": "ProjectVersion",
    "created_at": "CreatedAt",
    "updated_at": "LastUpdatedOn",
    "last_updated_on": "LastUpdatedOn",
    "status": "Status"
}

DOC_MAPPING = {
    "document_id": "DocumentId",
    "filename": "FileName",
    "file_size": "FileSize",
    "pages": "Pages",
    "upload_date": "UploadDate",
    "uploaded_by": "UploadedBy",
    "status": "Status",
    "document_path": "DocumentPath",
}

def migrate_dict(d, mapping):
    new_d = {}
    for k, v in d.items():
        new_key = mapping.get(k, k)
        new_d[new_key] = v
    return new_d

if os.path.exists(ROOT):
    print(f"Starting comprehensive metadata migration in {ROOT}...")
    for p in os.listdir(ROOT):
        dir_path = os.path.join(ROOT, p)
        if not os.path.isdir(dir_path): continue
        meta_path = os.path.join(dir_path, 'Metadata', 'project.json')
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f: data = json.load(f)
                
                # Migrate top-level fields
                migrated_data = migrate_dict(data, MAPPING)
                
                # Migrate documents
                if 'documents' in migrated_data:
                    new_docs = []
                    for doc in migrated_data['documents']:
                        new_docs.append(migrate_dict(doc, DOC_MAPPING))
                    migrated_data['documents'] = new_docs
                
                # Force ProjectVersion if missing
                if not migrated_data.get('ProjectVersion'):
                    migrated_data['ProjectVersion'] = "1.0"
                
                # Force Tool if missing (default to None)
                if not migrated_data.get('Tool'):
                    migrated_data['Tool'] = "None"

                # Force Status if missing (default to active)
                if not migrated_data.get('Status'):
                    migrated_data['Status'] = "active"

                # Cleanup old keys
                keys_to_delete = [k for k in MAPPING.keys() if k in migrated_data and k != MAPPING[k]]
                for k in keys_to_delete:
                    del migrated_data[k]

                with open(meta_path, 'w') as f:
                    json.dump(migrated_data, f, indent=2)
                print(f"✅ Successfully migrated: {p}")
                
            except Exception as e:
                print(f"❌ Error migrating {p}: {e}")
else:
    print(f"Directory not found: {ROOT}")
