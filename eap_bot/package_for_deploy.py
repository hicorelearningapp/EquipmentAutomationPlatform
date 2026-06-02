import os
import zipfile

def create_zip():
    zip_filename = "eap_bot_package.zip"
    dirs_to_include = ["source", "GEMTestScriptTemplates", "MESMapTemplates"]
    files_to_include = ["requirements.txt", ".env"]

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for f in files_to_include:
            if os.path.exists(f):
                zipf.write(f, arcname=f)
        
        for d in dirs_to_include:
            if os.path.exists(d):
                for root, dirs, files in os.walk(d):
                    # Skip __pycache__
                    if "__pycache__" in root:
                        continue
                    for file in files:
                        if file.endswith(".pyc"):
                            continue
                        file_path = os.path.join(root, file)
                        # Replace backslashes with forward slashes for arcname
                        arcname = os.path.relpath(file_path, ".").replace("\\", "/")
                        zipf.write(file_path, arcname=arcname)
                        
    print("Created zip successfully with forward slashes!")

if __name__ == "__main__":
    create_zip()
