import os
import json
import pytest
from fastapi.testclient import TestClient

# Make sure we can import the app
try:
    from source.main import app
except ImportError:
    # Fallback if running from a different directory
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from source.main import app

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c

# Store results
results_list = []

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # execute all other hooks to obtain the report object
    outcome = yield
    rep = outcome.get_result()

    # we only look at actual failing/passing test calls, not setup/teardown
    if rep.when == 'call':
        # Grab properties recorded by the test
        props = dict(item.user_properties)
        method = props.get("method", "UNKNOWN")
        url = props.get("url", item.name)
        expected = props.get("expected", "-")
        got = props.get("got", "-")
        
        # Extract the test file base name (e.g., "test_documents_endpoints.py")
        file_name = "unknown_test.py"
        if item.nodeid:
            file_name = os.path.basename(item.nodeid.split("::")[0])
        
        results_list.append({
            "test_name": item.name,
            "file_name": file_name,
            "method": method,
            "url": url,
            "status": rep.outcome,  # 'passed', 'failed', 'skipped'
            "duration_ms": int(rep.duration * 1000),
            "expected": expected,
            "got": got,
            "error_msg": str(rep.longrepr) if rep.failed else None
        })

def _write_ascii_table(file_path, results):
    with open(file_path, "w", encoding="utf-8") as f:
        # Fixed widths: Status(12), Method(8), Endpoint(50), Assertion(60)
        f.write("┌" + "─"*13 + "┬" + "─"*8 + "┬" + "─"*52 + "┬" + "─"*32 + "┐\n")
        f.write("│ Status      │ Method │ Endpoint                                           │ Result                         │\n")
        f.write("├" + "─"*13 + "┼" + "─"*8 + "┼" + "─"*52 + "┼" + "─"*32 + "┤\n")
        
        for res in results:
            if res["status"] == "passed":
                status_str = "🟢 [PASS] "
            elif res["status"] == "failed":
                status_str = "🔴 [FAIL] "
            else:
                status_str = "🟡 [SKIP] "
            
            method = res["method"].ljust(6)
            url = res["url"]
            if len(url) > 50:
                url = url[:47] + "..."
            url = url.ljust(50)
            
            assertion = f"Expected {res['expected']}, Got {res['got']}"
            assertion = assertion.ljust(30)
            
            f.write(f"│ {status_str}  │ {method} │ {url} │ {assertion} │\n")
            
        f.write("└" + "─"*13 + "┴" + "─"*8 + "┴" + "─"*52 + "┴" + "─"*32 + "┘\n")
        
        # Add error details if any
        failures = [r for r in results if r["status"] == "failed" and r["error_msg"]]
        if failures:
            f.write("\n\n=== FAILURE DETAILS ===\n")
            for res in failures:
                f.write(f"\n--- {res['test_name']} ---\n")
                f.write(res["error_msg"] + "\n")

def pytest_sessionfinish(session, exitstatus):
    # Compute log_dir relative to this file's location to ensure it is always in the correct workspace path
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    log_dir = os.path.join(project_root, "test_logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # 1. Write JSON
    json_path = os.path.join(log_dir, "results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results_list, f, indent=2)
        
    # 2. Write Combined ASCII Table
    table_path = os.path.join(log_dir, "results_table.log")
    _write_ascii_table(table_path, results_list)
    
    # 3. Write Individual Log Files for each test script
    # Group results by file_name
    by_file = {}
    for res in results_list:
        by_file.setdefault(res["file_name"], []).append(res)
        
    for file_name, file_results in by_file.items():
        if file_name.endswith(".py"):
            log_name = file_name[:-3] + ".log"
            individual_path = os.path.join(log_dir, log_name)
            _write_ascii_table(individual_path, file_results)
