import os, json

ROOT = '/root/eap_bot/projects'

MAPPING = {
    "ProjectID": "ProjectID",
    "ProjectName": "ProjectName",
    "VendorName": "VendorName",
    "Tool": "Tool",
    "CreatedAt": "CreatedAt",
    "LastUpdatedOn": "LastUpdatedOn",
    "Status": "Status",
    "document_count": "DocumentCount",
    "documents": "Documents"
}

DOC_MAPPING = {
    "DocumentId": "DocumentId",
    "DocumentType": "DocumentType",
    "FileName": "FileName",
    "FileSize": "FileSize",
    "Pages": "Pages",
    "UploadDate": "UploadDate",
    "UploadedBy": "UploadedBy",
    "Status": "Status",
    "DocumentPath": "DocumentPath",
    "json_path": "JsonPath",
    "tool_id": "ToolId",
    "tool_type": "ToolType",
    "vector_indexed": "VectorIndexed"
}

def migrate_dict(d, mapping):
    new_d = {}
    for k, v in d.items():
        new_key = mapping.get(k, k)
        new_d[new_key] = v
    # Cleanup old keys if they were renamed
    keys_to_del = [k for k in mapping.keys() if k in new_d and k != mapping[k]]
    for k in keys_to_del:
        del new_d[k]
    return new_d

if os.path.exists(ROOT):
    print(f"Starting Final PascalCase Migration in {ROOT}...")
    for p in os.listdir(ROOT):
        dir_path = os.path.join(ROOT, p)
        if not os.path.isdir(dir_path): continue
        meta_path = os.path.join(dir_path, 'Metadata', 'project.json')
        if os.path.exists(meta_path):
            try:
                with open(meta_path, 'r') as f: data = json.load(f)
                
                # 1. Map top-level
                data = migrate_dict(data, MAPPING)
                
                # 2. Map documents
                if 'Documents' in data:
                    new_docs = []
                    for doc in data['Documents']:
                        new_docs.append(migrate_dict(doc, DOC_MAPPING))
                    data['Documents'] = new_docs
                
                # 3. Ensure mandatory fields for validation
                if not data.get('VendorName'): data['VendorName'] = "Unknown"
                
                with open(meta_path, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"✅ Migrated PascalCase: {p}")
            except Exception as e:
                print(f"❌ Error migrating {p}: {e}")
else:
    print(f"Directory not found: {ROOT}")
