import urllib.request
import json
import sys

try:
    r = urllib.request.urlopen('http://localhost:8012/LoadProject/13')
    d = json.loads(r.read())
    reports = d['Extractions'].get('Reports', [])
    print(f"Number of reports returned from LoadProject: {len(reports)}")
    if reports:
        print(json.dumps(reports[0], indent=2))
except Exception as e:
    print(f"Error: {e}")
