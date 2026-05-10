import os, json

ROOT = '/root/eap_bot/projects'

def migrate_project(meta_path):
    try:
        with open(meta_path, 'r') as f:
            data = json.load(f)
        
        changed = False
        
        # 1. Remove ProjectVersion
        if 'ProjectVersion' in data:
            del data['ProjectVersion']
            changed = True
            
        # 2. Add DocumentType to documents
        if 'documents' in data:
            for doc in data['documents']:
                if 'DocumentType' not in doc:
                    doc['DocumentType'] = "User Manuals"
                    changed = True
        
        if changed:
            with open(meta_path, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"✅ Migrated: {meta_path}")
        else:
            print(f"ℹ️ No changes needed for: {meta_path}")
            
    except Exception as e:
        print(f"❌ Error migrating {meta_path}: {e}")

if os.path.exists(ROOT):
    print(f"Starting metadata migration V2 in {ROOT}...")
    for p in os.listdir(ROOT):
        dir_path = os.path.join(ROOT, p)
        if not os.path.isdir(dir_path): continue
        meta_path = os.path.join(dir_path, 'Metadata', 'project.json')
        if os.path.exists(meta_path):
            migrate_project(meta_path)
else:
    print(f"Directory not found: {ROOT}")
