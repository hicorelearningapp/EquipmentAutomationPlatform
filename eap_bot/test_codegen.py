import requests
import json

data = {
    "ProjectID": 4,
    "FileName": "collect_data.py",
    "Language": "python",
    "Instructions": "Generate a script to collect all Status Variables every 10 seconds."
}

res = requests.post("http://localhost:8012/GenerateCode", json=data)
print(res.status_code)
print(json.dumps(res.json(), indent=2))
