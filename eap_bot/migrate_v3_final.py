import os, json

ROOT = '/root/eap_bot/projects'

# Comprehensive mapping for all historical variations
PROJECT_MAPPING = {
    "id": "ProjectID",
    "project_id": "ProjectID",
    "name": "ProjectName",
    "project_name": "ProjectName",
    "vendor_name": "VendorName",
    "tool": "Tool",
    "created_at": "CreatedAt",
    "updated_at": "LastUpdatedOn",
    "last_updated_on": "LastUpdatedOn",
    "status": "Status"
}

DOC_MAPPING = {
    "id": "DocumentId",
    "document_id": "DocumentId",
    "original_filename": "FileName",
    "filename": "FileName",
    "file_size": "FileSize",
    "pages": "Pages",
    "upload_date": "UploadDate",
    "uploaded_at": "UploadDate",
    "status": "Status",
    "extraction_status": "Status",
    "document_path": "DocumentPath",
    "pdf_path": "DocumentPath",
}

def migrate_dict(d, mapping):
    new_d = {}
    for k, v in d.items():
        new_key = mapping.get(k, k)
        new_d[new_key] = v
    # Remove old keys if they were renamed
    for old_key in mapping.keys():
        if old_key in new_d and old_key != mapping[old_key]:
            del new_d[old_key]
    return new_d

def migrate_project(meta_path):
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
        
        # 1. Migrate Project level
        data = migrate_dict(data, PROJECT_MAPPING)
        
        # 2. Migrate Documents
        if 'documents' in data:
            new_docs = []
            for doc in data['documents']:
                migrated_doc = migrate_dict(doc, DOC_MAPPING)
                # Ensure DocumentType exists
                if 'DocumentType' not in migrated_doc:
                    migrated_doc['DocumentType'] = "User Manuals"
                # Ensure tool-related fields are present (snake_case in schema)
                for field in ["json_path", "tool_id", "tool_type", "vector_indexed"]:
                    if field not in migrated_doc:
                        if field == "vector_indexed": migrated_doc[field] = False
                        else: migrated_doc[field] = ""
                new_docs.append(migrated_doc)
            data['documents'] = new_docs
        
        # 3. Cleanup ProjectVersion if any
        if 'ProjectVersion' in data:
            del data['ProjectVersion']

        # 4. Final safety defaults
        if not data.get('Tool'): data['Tool'] = "None"
        if not data.get('Status'): data['Status'] = "active"

        with open(meta_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"✅ Fully Migrated: {meta_path}")
            
    except Exception as e:
        print(f"❌ Error migrating {meta_path}: {e}")

if os.path.exists(ROOT):
    print(f"Starting Final Comprehensive Migration in {ROOT}...")
    for p in os.listdir(ROOT):
        dir_path = os.path.join(ROOT, p)
        if not os.path.isdir(dir_path): continue
        meta_path = os.path.join(dir_path, 'Metadata', 'project.json')
        if os.path.exists(meta_path):
            migrate_project(meta_path)
else:
    print(f"Directory not found: {ROOT}")
