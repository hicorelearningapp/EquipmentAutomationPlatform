import os

# ==========================
# CONFIGURATION
# ==========================

ROOT_FOLDER = r"E:\Github\EquipmentAutomationPlatform\eap_bot"      # Change this
OUTPUT_FILE = f"project_code_dump_{os.path.basename(ROOT_FOLDER)}.txt"

# Ignore these folders completely
EXCLUDED_FOLDERS = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    "db helpers"
}

# Ignore these filenames
EXCLUDED_FILES = {
    OUTPUT_FILE,
    ".DS_Store",
    ".env",
    "config.py"
}

# Ignore these file extensions
EXCLUDED_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".exe",
    ".dll",
    ".so",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".log",
    ".csv",
    ".xlsx",
    ".xls",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".mp3",
    ".wav",
    ".mp4",
    ".avi",
    ".mov",
    ".ttf",
    ".otf",
}

# ==========================
# SCRIPT
# ==========================

with open(OUTPUT_FILE, "w", encoding="utf-8") as outfile:

    for root, dirs, files in os.walk(ROOT_FOLDER):

        # Remove excluded folders from traversal
        dirs[:] = [d for d in dirs if d not in EXCLUDED_FOLDERS]

        for file in sorted(files):

            if file in EXCLUDED_FILES:
                continue

            extension = os.path.splitext(file)[1].lower()

            if extension in EXCLUDED_EXTENSIONS:
                continue

            filepath = os.path.join(root, file)

            relative_path = os.path.relpath(filepath, ROOT_FOLDER)

            try:
                with open(filepath, "r", encoding="utf-8") as infile:
                    content = infile.read()
            except UnicodeDecodeError:
                try:
                    with open(filepath, "r", encoding="latin-1") as infile:
                        content = infile.read()
                except Exception:
                    print(f"Skipped (encoding): {relative_path}")
                    continue
            except Exception as e:
                print(f"Skipped: {relative_path} ({e})")
                continue

            outfile.write("=" * 100 + "\n")
            outfile.write(f"FILE: {relative_path}\n")
            outfile.write("=" * 100 + "\n\n")

            outfile.write(content)
            outfile.write("\n\n\n")

print(f"\nDone! Output written to {OUTPUT_FILE}")