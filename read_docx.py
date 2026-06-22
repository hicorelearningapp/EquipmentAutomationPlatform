import sys
import subprocess

try:
    from docx import Document
except ImportError:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'python-docx', '--quiet'])
    from docx import Document

doc_path = r'e:\Github\EquipmentAutomationPlatforms\SML_Test_Script_v2_updated.docx'
out_path = r'C:\Users\Jennica\.gemini\antigravity-ide\brain\6e7109e2-347d-46e1-87fe-b7be3dbc6879\scratch\extracted_sml_template.txt'
try:
    doc = Document(doc_path)
    lines = []
    for para in doc.paragraphs:
        lines.append(para.text)
    
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    print(f"Successfully extracted document to: {out_path}")
except Exception as e:
    print(f"Error reading document: {e}")
