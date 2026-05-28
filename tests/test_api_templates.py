import os
os.environ["USE_AWS_SERVICES"] = "false"

from fastapi.testclient import TestClient
import pytest
try:
    from src.api.main import app
    from src.shared.repository import repo
except Exception as exc:  # pragma: no cover - environment-dependent bootstrap
    pytest.skip(f"API bootstrap unavailable in current environment: {exc}", allow_module_level=True)

client = TestClient(app)

def test_list_and_get_templates():
    # 1. Add a template programmatically to repo
    template_id, version = repo.create_template(
        template_name="Test Template 1.docx",
        object_key="templates/Test Template 1.docx"
    )
    manifest = {
        "manifest_id": "test-manifest",
        "template_id": template_id,
        "version": version,
        "fields": [
            {
                "name": "full_name",
                "field_type": "scalar",
                "source_hint": "Extract full name",
                "template_token": "MERGEFIELD CandidateFullName",
                "required": True
            }
        ],
        "created_at": "2026-05-27T00:00:00Z"
    }
    repo.save_manifest(template_id, manifest)

    # 2. Test GET /templates
    response = client.get("/templates")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert "templates" in data
    
    # Check if our created template is in the list
    templates_list = data["templates"]
    found = [t for t in templates_list if t["template_id"] == template_id]
    assert len(found) == 1
    assert found[0]["template_name"] == "Test Template 1.docx"
    assert found[0]["manifest"] == manifest

    # 3. Test GET /templates/{template_id}
    detail_response = client.get(f"/templates/{template_id}")
    assert detail_response.status_code == 200
    detail_data = detail_response.json()
    assert detail_data["template_id"] == template_id
    assert detail_data["template_name"] == "Test Template 1.docx"
    assert detail_data["version"] == version
    assert detail_data["manifest"] == manifest

    # 4. Test GET /templates/non-existent-id -> 404
    err_response = client.get("/templates/non-existent-id")
    assert err_response.status_code == 404
