import sys
import subprocess

try:
    from docx import Document
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-docx', '--quiet'])
    from docx import Document

doc_path = r'e:\Github\EquipmentAutomationPlatforms\Extraction Requirements.docx'
try:
    doc = Document(doc_path)
    for i, para in enumerate(doc.paragraphs):
        print(f"{i}: {para.text}")
except Exception as e:
    print(f"Error reading document: {e}")
