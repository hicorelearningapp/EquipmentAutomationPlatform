import requests
import os

BASE_URL = "http://localhost:8000"
PROJECT_ID = "testproject"
FILE_PATH = "e:/Github/EquipmentAutomationPlatform/eap_bot/runtime_storage/frontend_etch_module/Documents/plasma_etching_system_fem.pdf"

def test_workflow():
    print(f"Testing workflow for project: {PROJECT_ID}")
    
    # 1. Upload Document
    print("\n[1/3] Testing UploadDocument...")
    with open(FILE_PATH, "rb") as f:
        files = {"file": (os.path.basename(FILE_PATH), f, "application/pdf")}
        response = requests.post(f"{BASE_URL}/UploadDocument/{PROJECT_ID}", files=files)
    
    if response.status_code == 200:
        data = response.json()
        doc_id = data["DocumentID"]
        print(f"SUCCESS: Uploaded document. DocumentID: {doc_id}")
    else:
        print(f"FAILED: {response.text}")
        return

    # 2. Test Analyze
    print("\n[2/3] Testing Analyze...")
    response = requests.get(f"{BASE_URL}/Analyze/{PROJECT_ID}/{doc_id}")
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Analysis completed. Status: {data['ExtractionStatus']}")
        print(f"Found {len(data['StatusVariables'])} SVs and {len(data['Events'])} Events.")
    else:
        print(f"FAILED: {response.text}")

    # 3. Test LoadProject (Batch processing)
    print("\n[3/3] Testing LoadProject (Batch)...")
    response = requests.get(f"{BASE_URL}/LoadProject/{PROJECT_ID}")
    if response.status_code == 200:
        data = response.json()
        print(f"SUCCESS: Project loaded. Document Count: {data['document_count']}")
        for doc in data["documents"]:
            print(f" - {doc['DocumentId']}: {doc['Status']}")
    else:
        print(f"FAILED: {response.text}")

if __name__ == "__main__":
    test_api_key = os.getenv("GROQ_API_KEY")
    if not test_api_key:
        print("WARNING: GROQ_API_KEY not found in environment. Analyze might fail.")
    test_workflow()
