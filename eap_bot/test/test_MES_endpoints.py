"""
test_mes_family_api.py
======================
Test suite for the 6 MES Family / Template endpoints using pytest and TestClient.
"""

import io
import json
import pytest

# Configuration
TARGET_FAMILY = "FAB300"
TEMP_FAMILY_NAME = "TestFamily_TEMP_XYZ"
TEST_TEMPLATE_NAME = "TEST_AUTO_TEMPLATE_DO_NOT_USE"
SEEDED_FAMILIES = [
    "FactoryWorks", "FAB300", "PROMIS", "Camstar",
    "Critical Manufacturing", "Custom MES"
]

def _template_payload(mes_family: str, template_name: str) -> dict:
    return {
        "MESFamily": mes_family,
        "TemplateName": template_name,
        "Version": "1.0",
        "Description": "Automated test template — safe to delete",
        "Events": [], "Alarms": [], "Variables": [], "Payloads": [], "Transactions": [],
        "ValidationRules": [], "AutoMapping": {"Enabled": True}, "Logging": {"Enabled": True}
    }

def _current_families(client):
    r = client.get("/GetMesFamilies")
    data = r.json()
    return data if isinstance(data, list) else data.get("MESFamilies", [])

# ── Group 1 — GET /GetMesFamilies ──────────────────────────────────────────────

def test_get_mes_families(client, record_property):
    record_property("method", "GET")
    record_property("url", "/GetMesFamilies")
    response = client.get("/GetMesFamilies")
    
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200

    families = response.json()
    if isinstance(families, dict):
        families = families.get("MESFamilies", [])

    names = [f.get("Family") for f in families]
    missing_names = [s for s in SEEDED_FAMILIES if s not in names]
    assert not missing_names, f"missing seeded families: {missing_names}"

    required_keys = {"Family", "DefaultProtocol", "RequiresAck", "Description"}
    for f in families:
        assert required_keys.issubset(f.keys()), f"incomplete entry: {f.get('Family', '?')}"
        assert f.get("FamilyID") is not None, f"missing FamilyID in {f.get('Family')}"


# ── Group 2 — POST /UpdateMesFamilies ──────────────────────────────────────────

def test_update_mes_families_add_new(client, record_property):
    record_property("method", "POST")
    record_property("url", "/UpdateMesFamilies")
    current = _current_families(client)
    new_entry = {
        "FamilyID": None,
        "Family": TEMP_FAMILY_NAME,
        "DefaultProtocol": "REST/JSON",
        "RequiresAck": False,
        "Description": "Temporary family created by automated test",
    }
    
    response = client.post("/UpdateMesFamilies", json=current + [new_entry])
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    body = response.json()
    returned_families = body.get("Families", [])
    returned_names = [f["Family"] for f in returned_families]
    
    assert TEMP_FAMILY_NAME in returned_names
    assert body.get("Status") == "success"

def test_update_mes_families_duplicate_name(client, record_property):
    record_property("method", "POST")
    record_property("url", "/UpdateMesFamilies")
    current = _current_families(client)
    new_entry = {
        "FamilyID": None,
        "Family": TEMP_FAMILY_NAME,
        "DefaultProtocol": "REST/JSON",
        "RequiresAck": False,
        "Description": "Temporary family created by automated test",
    }
    dup_name_list = current + [new_entry, {**new_entry, "FamilyID": None}]
    
    response = client.post("/UpdateMesFamilies", json=dup_name_list)
    record_property("expected", 400)
    record_property("got", response.status_code)
    assert response.status_code == 400
    assert "duplicate" in str(response.json()).lower()

def test_update_mes_families_duplicate_id(client, record_property):
    record_property("method", "POST")
    record_property("url", "/UpdateMesFamilies")
    current = _current_families(client)
    if len(current) >= 2:
        dup_id_list = json.loads(json.dumps(current))
        dup_id_list[1]["FamilyID"] = dup_id_list[0]["FamilyID"]
        response = client.post("/UpdateMesFamilies", json=dup_id_list)
        record_property("expected", 400)
        record_property("got", response.status_code)
        assert response.status_code == 400
        assert "duplicate" in str(response.json()).lower()

def test_update_mes_families_remove_temp(client, record_property):
    record_property("method", "POST")
    record_property("url", "/UpdateMesFamilies")
    current = _current_families(client)
    clean_list = [f for f in current if f["Family"] != TEMP_FAMILY_NAME]
    
    response = client.post("/UpdateMesFamilies", json=clean_list)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    final_names = [f["Family"] for f in response.json().get("Families", [])]
    assert TEMP_FAMILY_NAME not in final_names


# ── Group 3 — GET /GetMesTemplates/{mes_family} ────────────────────────────────

def test_get_mes_templates_known_family(client, record_property):
    url = f"/GetMesTemplates/{TARGET_FAMILY}"
    record_property("method", "GET")
    record_property("url", url)
    
    response = client.get(url)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    templates = response.json()
    assert isinstance(templates, list)
    has_seed = any("STANDARD_EVENT_MODEL" in t for t in templates)
    assert has_seed, "STANDARD_EVENT_MODEL.json is present"

def test_get_mes_templates_unknown_family(client, record_property):
    url = "/GetMesTemplates/NonExistentFamily_XYZZY"
    record_property("method", "GET")
    record_property("url", url)
    
    response = client.get(url)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404
    assert "nonexistentfamily_xyzzy" in str(response.json()).lower()

def test_get_mes_templates_known_empty(client, record_property):
    url = "/GetMesTemplates/Custom MES"
    record_property("method", "GET")
    record_property("url", url)
    
    response = client.get(url)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    templates = response.json()
    assert isinstance(templates, list)


# ── Group 4 — GET /GetMesTemplateInfo/{mes_family}/{template} ──────────────────

def test_get_mes_template_info_valid(client, record_property):
    url = f"/GetMesTemplateInfo/{TARGET_FAMILY}/STANDARD_EVENT_MODEL.json"
    record_property("method", "GET")
    record_property("url", url)
    
    response = client.get(url)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    
    expected_keys = {"Events", "Alarms", "Variables", "Payloads", "Transactions", "ValidationRules", "AutoMapping", "Logging"}
    body = response.json()
    missing = expected_keys - body.keys()
    assert not missing

def test_get_mes_template_info_nonexistent(client, record_property):
    url = f"/GetMesTemplateInfo/{TARGET_FAMILY}/ghost_XYZZY.json"
    record_property("method", "GET")
    record_property("url", url)
    
    response = client.get(url)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_get_mes_template_info_nonexistent_family(client, record_property):
    url = "/GetMesTemplateInfo/FakeFamily_XYZZY/STANDARD_EVENT_MODEL"
    record_property("method", "GET")
    record_property("url", url)
    
    response = client.get(url)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_get_mes_template_info_no_ext(client, record_property):
    url = f"/GetMesTemplateInfo/{TARGET_FAMILY}/STANDARD_EVENT_MODEL"
    record_property("method", "GET")
    record_property("url", url)
    
    response = client.get(url)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    expected_keys = {"Events", "Alarms", "Variables", "Payloads", "Transactions", "ValidationRules", "AutoMapping", "Logging"}
    body = response.json()
    missing = expected_keys - body.keys()
    assert not missing


# ── Group 5 — POST /AddMesTemplateInfo/{mes_family} ────────────────────────────

def _upload_template(client, mes_family: str, filename: str, payload, content_type="application/json"):
    data = json.dumps(payload).encode() if isinstance(payload, dict) else payload
    files = {"file": (filename, io.BytesIO(data), content_type)}
    return client.post(f"/AddMesTemplateInfo/{mes_family}", files=files)

def test_add_mes_template_valid(client, record_property):
    url = f"/AddMesTemplateInfo/{TARGET_FAMILY}"
    record_property("method", "POST")
    record_property("url", url)
    
    payload = _template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)
    response = _upload_template(client, TARGET_FAMILY, f"{TEST_TEMPLATE_NAME}.json", payload)
    
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code in [200, 409] # Allow 409 if it already exists from a previous run


def test_add_mes_template_duplicate(client, record_property):
    url = f"/AddMesTemplateInfo/{TARGET_FAMILY}"
    record_property("method", "POST")
    record_property("url", url)
    
    payload = _template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)
    _upload_template(client, TARGET_FAMILY, f"{TEST_TEMPLATE_NAME}.json", payload) # Ensure it exists
    
    response = _upload_template(client, TARGET_FAMILY, f"{TEST_TEMPLATE_NAME}.json", payload)
    record_property("expected", 409)
    record_property("got", response.status_code)
    assert response.status_code == 409

def test_add_mes_template_invalid_ext(client, record_property):
    url = f"/AddMesTemplateInfo/{TARGET_FAMILY}"
    record_property("method", "POST")
    record_property("url", url)
    
    response = _upload_template(client, TARGET_FAMILY, "wrong_extension.txt", b"not json", "text/plain")
    record_property("expected", 400)
    record_property("got", response.status_code)
    assert response.status_code == 400

def test_add_mes_template_invalid_json(client, record_property):
    url = f"/AddMesTemplateInfo/{TARGET_FAMILY}"
    record_property("method", "POST")
    record_property("url", url)
    
    response = _upload_template(client, TARGET_FAMILY, "invalid.json", b"{this is not valid json!!!}")
    record_property("expected", 400)
    record_property("got", response.status_code)
    assert response.status_code == 400

def test_add_mes_template_mismatched_family(client, record_property):
    url = f"/AddMesTemplateInfo/{TARGET_FAMILY}"
    record_property("method", "POST")
    record_property("url", url)
    
    wrong_payload = _template_payload("PROMIS", TEST_TEMPLATE_NAME)
    response = _upload_template(client, TARGET_FAMILY, f"{TEST_TEMPLATE_NAME}_mismatch.json", wrong_payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422

def test_add_mes_template_nonexistent_family(client, record_property):
    url = "/AddMesTemplateInfo/FakeFamily_XYZZY"
    record_property("method", "POST")
    record_property("url", url)
    
    payload = _template_payload("FakeFamily_XYZZY", TEST_TEMPLATE_NAME)
    response = _upload_template(client, "FakeFamily_XYZZY", f"{TEST_TEMPLATE_NAME}.json", payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404


# ── Group 6 — PUT /UpdateMesTemplateInfo/{mes_family}/{template} ───────────────

def _update_template(client, mes_family: str, template: str, payload: dict, filename: str = None, content_type="application/json"):
    fname = filename or f"{template}.json"
    data = json.dumps(payload).encode()
    files = {"file": (fname, io.BytesIO(data), content_type)}
    return client.put(f"/UpdateMesTemplateInfo/{mes_family}/{template}", files=files)

def test_update_mes_template_valid(client, record_property):
    url = f"/UpdateMesTemplateInfo/{TARGET_FAMILY}/{TEST_TEMPLATE_NAME}"
    record_property("method", "PUT")
    record_property("url", url)
    
    updated_payload = _template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)
    del updated_payload["Version"]
    
    response = _update_template(client, TARGET_FAMILY, TEST_TEMPLATE_NAME, updated_payload)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200

def test_update_mes_template_mismatch(client, record_property):
    url = f"/UpdateMesTemplateInfo/{TARGET_FAMILY}/{TEST_TEMPLATE_NAME}"
    record_property("method", "PUT")
    record_property("url", url)
    
    mismatch_payload = _template_payload("PROMIS", TEST_TEMPLATE_NAME)
    response = _update_template(client, TARGET_FAMILY, TEST_TEMPLATE_NAME, mismatch_payload)
    record_property("expected", 422)
    record_property("got", response.status_code)
    assert response.status_code == 422

def test_update_mes_template_explicit_version(client, record_property):
    url = f"/UpdateMesTemplateInfo/{TARGET_FAMILY}/{TEST_TEMPLATE_NAME}"
    record_property("method", "PUT")
    record_property("url", url)
    
    payload = _template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)
    payload["Version"] = "3.0"
    
    response = _update_template(client, TARGET_FAMILY, TEST_TEMPLATE_NAME, payload)
    record_property("expected", 200)
    record_property("got", response.status_code)
    assert response.status_code == 200
    assert response.json().get("Version") == "3.0"

def test_update_mes_template_nonexistent(client, record_property):
    url = f"/UpdateMesTemplateInfo/{TARGET_FAMILY}/ghost_template_XYZZY"
    record_property("method", "PUT")
    record_property("url", url)
    
    payload = _template_payload(TARGET_FAMILY, "ghost")
    response = _update_template(client, TARGET_FAMILY, "ghost_template_XYZZY", payload)
    record_property("expected", 404)
    record_property("got", response.status_code)
    assert response.status_code == 404

def test_update_mes_template_invalid_ext(client, record_property):
    url = f"/UpdateMesTemplateInfo/{TARGET_FAMILY}/{TEST_TEMPLATE_NAME}"
    record_property("method", "PUT")
    record_property("url", url)
    
    payload = _template_payload(TARGET_FAMILY, TEST_TEMPLATE_NAME)
    response = _update_template(client, TARGET_FAMILY, TEST_TEMPLATE_NAME, payload, filename="bad.txt", content_type="text/plain")
    record_property("expected", 400)
    record_property("got", response.status_code)
    assert response.status_code == 400

def test_update_mes_template_invalid_json(client, record_property):
    url = f"/UpdateMesTemplateInfo/{TARGET_FAMILY}/{TEST_TEMPLATE_NAME}"
    record_property("method", "PUT")
    record_property("url", url)
    
    bad_bytes = b"{this is not json!}"
    files = {"file": (f"{TEST_TEMPLATE_NAME}.json", io.BytesIO(bad_bytes), "application/json")}
    response = client.put(url, files=files)
    record_property("expected", 400)
    record_property("got", response.status_code)
    assert response.status_code == 400

if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__]))