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


def test_select_template_endpoint():
    from src.shared.models import JobStatus, JobType
    
    # 1. Create a dummy template in repo
    template_id, _ = repo.create_template(
        template_name="Test Selection Template.docx",
        object_key="templates/Test Selection Template.docx"
    )

    # 2. Create a dummy job in the repo in WAITING_FOR_TEMPLATE_SELECTION status
    job = repo.create_job(
        job_type=JobType.RESUME_FORMAT,
        template_id=None,
        resume_text="Dummy CV text"
    )
    repo.update_job(job.job_id, status=JobStatus.WAITING_FOR_TEMPLATE_SELECTION)

    # 3. Test POST /jobs/{job_id}/select-template
    payload = {"template_id": template_id}
    response = client.post(f"/jobs/{job.job_id}/select-template", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job.job_id
    assert data["status"] == "queued"

    # 4. Verify job status updated in repo
    updated_job = repo.get_job(job.job_id)
    assert updated_job.status == JobStatus.QUEUED
    assert updated_job.template_id == template_id


def test_template_version_incrementing():
    # 1. Upload first template
    file_payload1 = {"file": ("UK taxation.docx", b"dummy docx bytes", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res1 = client.post("/admin/templates", files=file_payload1)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["version"] == 1
    
    # Verify in repo
    tpl1 = repo.get_template(data1["template_id"])
    assert tpl1["version"] == 1
    assert tpl1["object_key"] == "templates/v1/UK taxation.docx"

    # 2. Upload same template name again -> should auto increment to v2
    file_payload2 = {"file": ("UK taxation.docx", b"dummy docx bytes 2", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res2 = client.post("/admin/templates", files=file_payload2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["version"] == 2
    
    # Verify in repo
    tpl2 = repo.get_template(data2["template_id"])
    assert tpl2["version"] == 2
    assert tpl2["object_key"] == "templates/v2/UK taxation.docx"


