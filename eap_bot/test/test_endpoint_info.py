from fastapi.testclient import TestClient
from source.main import app
import traceback
import sys

client = TestClient(app)
try:
    response = client.get('/EndpointInfo?endpoint_path=/UpdateExtraction')
    print("STATUS:", response.status_code)
    print("BODY:", response.text)
except Exception as e:
    traceback.print_exc()
