import requests
import json

payload = {
  "equipment_spec": {
    "StatusVariables": [
      {
        "SVID": 9501,
        "Name": "ChamberTemperature",
        "Description": "Current chamber temperature",
        "DataType": "Float",
        "AccessType": "Read"
      }
    ],
    "DataVariables": [],
    "Events": [],
    "Alarms": []
  },
  "family": "FactoryWorks",
  "template": "STANDARD_EVENT_MODEL.json"
}

response = requests.post(
    "http://151.185.41.194:8012/AutoMap",
    headers={"Content-Type": "application/json", "Accept": "application/json"},
    json=payload
)

print(f"Status Code: {response.status_code}")
try:
    print(json.dumps(response.json(), indent=2))
except:
    print(response.text)
