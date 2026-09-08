import argparse
import sys
import os
import json
import base64
import logging
from dotenv import load_dotenv
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from pathlib import Path
import tiktoken_ext.openai_public
import tiktoken_ext

# Load environment variables (like GROQ_API_KEY) from a .env file
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 32-byte key for AES-256. This MUST match the key in the C# app exactly!
SHARED_SECRET_KEY = b'MySuperSecretKey1234567890123456'

def encrypt_payload(data_dict_or_list):
    cipher = AES.new(SHARED_SECRET_KEY, AES.MODE_CBC)
    json_str = json.dumps(data_dict_or_list)
    encrypted_bytes = cipher.encrypt(pad(json_str.encode('utf-8'), AES.block_size))
    final_payload = cipher.iv + encrypted_bytes
    return base64.b64encode(final_payload).decode('utf-8')

def execute_api_call(method, url, output_path, json_payload=None, file_path=None, is_plain=False):
    """
    Acts as a universal proxy. Instantiates the FastAPI app internally,
    sends a virtual HTTP request, encrypts the response, and writes it to disk.
    """
    logger.info("Loading backend modules...")
    from fastapi.testclient import TestClient
    from source.main import app

    client = TestClient(app)
    
    kwargs = {}
    if file_path:
        # If both a file and json are provided, the json acts as the Form data (multipart/form-data)
        if json_payload:
            kwargs["data"] = json.loads(json_payload)
        with open(file_path, "rb") as f:
            # Replicate multipart/form-data upload
            kwargs["files"] = {"file": (os.path.basename(file_path), f)}
            logger.info(f"Executing {method} {url} with file payload...")
            response = client.request(method, url, **kwargs)
    else:
        if json_payload:
            kwargs["json"] = json.loads(json_payload)
        logger.info(f"Executing {method} {url}...")
        response = client.request(method, url, **kwargs)

    try:
        resp_data = response.json()
    except Exception:
        resp_data = {"error": response.text, "status_code": response.status_code}

    if response.status_code >= 400:
        logger.error(f"API Error ({response.status_code}): {resp_data}")

    if is_plain:
        logger.info("Writing plain JSON output payload (unencrypted)...")
        with open(output_path, 'w', encoding='utf-8') as out_f:
            json.dump(resp_data, out_f, indent=2)
    else:
        logger.info("Encrypting output payload...")
        encrypted_result = encrypt_payload(resp_data)
        with open(output_path, 'w', encoding='utf-8') as out_f:
            out_f.write(encrypted_result)
        
    logger.info(f"Execution completed securely. Output saved to '{output_path}'.")


def execute_legacy_extract(input_path, output_path, is_plain=False):
    """
    The original one-off temporary extraction command.
    Creates an isolated temporary database to leave no traces.
    """
    import tempfile
    if not os.path.exists(input_path):
        logger.error(f"Input file '{input_path}' does not exist.")
        sys.exit(1)

    try:
        # Override EAP_STORAGE_ROOT to a temporary directory so we don't mess with real databases
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["EAP_STORAGE_ROOT"] = temp_dir
            from source.config import settings
            settings.EAP_STORAGE_ROOT = temp_dir

            # Initialize backend container (bypass FastAPI)
            from source.managers.service_container import container
            from source.schemas.project import DocumentCategory, ProjectCreate
            
            logger.info("Initializing temporary workspace...")
            dummy_project = ProjectCreate(
                ProjectName="CLI Extraction", 
                Description="Temp CLI Project",
                VendorName="CLI Vendor",
                ProjectCode="CLI-999"
            )
            project_out = container.storage.create_project(dummy_project)
            project_id = project_out.ProjectID
            
            with open(input_path, "rb") as f:
                contents = f.read()
            
            filename = os.path.basename(input_path)

            logger.info("Uploading document to local engine...")
            upload_result = container.document_service.upload_document(
                project_id=project_id,
                filename=filename,
                contents=contents,
                doc_category=DocumentCategory.USER_MANUALS
            )

            document_id = upload_result["DocumentID"]

            logger.info("Analyzing document...")
            extraction_result = container.document_service.analyze_document(
                project_id=project_id,
                document_id=document_id
            )

            if is_plain:
                logger.info("Writing plain JSON output payload (unencrypted)...")
                with open(output_path, 'w', encoding='utf-8') as out_f:
                    json.dump(extraction_result, out_f, indent=2)
            else:
                logger.info("Encrypting output payload...")
                encrypted_result = encrypt_payload(extraction_result)
                with open(output_path, 'w', encoding='utf-8') as out_f:
                    out_f.write(encrypted_result)
                
            logger.info(f"Extraction completed securely. Output saved to '{output_path}'.")
            
    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Secure SECS/GEM Universal CLI")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # 1. New Generic API proxy command
    api_parser = subparsers.add_parser("api", help="Execute any backend API endpoint securely")
    api_parser.add_argument("--method", required=True, choices=["GET", "POST", "PUT", "DELETE"], help="HTTP Method")
    api_parser.add_argument("--url", required=True, help="Endpoint URL (e.g., /projects)")
    api_parser.add_argument("--output", required=True, help="Path to output file")
    api_parser.add_argument("--json", help="JSON payload string")
    api_parser.add_argument("--file", help="Path to a file for upload endpoints")
    api_parser.add_argument("--plain", action="store_true", help="Output plain JSON instead of AES encrypted data")

    # 2. Legacy extraction command
    extract_parser = subparsers.add_parser("extract", help="Shortcut to upload and analyze a PDF document in a temporary workspace")
    extract_parser.add_argument("--input", required=True, help="Path to input PDF document")
    extract_parser.add_argument("--output", required=True, help="Path to output file")
    extract_parser.add_argument("--plain", action="store_true", help="Output plain JSON instead of AES encrypted data")
    
    args = parser.parse_args()
    
    if args.command == "api":
        execute_api_call(args.method, args.url, args.output, args.json, args.file, args.plain)
    elif args.command == "extract":
        execute_legacy_extract(args.input, args.output, args.plain)
