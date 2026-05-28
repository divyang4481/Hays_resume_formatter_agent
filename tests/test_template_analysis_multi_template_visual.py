import pytest
from src.worker.agents.template_analysis.graph import run_template_analysis
import os

# We will test run_template_analysis against our 3 files
# Note: SampleData/templates may be missing in CI if not committed, but we assume it's here as requested.
# But for unit tests running locally, we need to read real bytes if possible.
# Wait, run_template_analysis uses `object_store` if we pass `template_bytes=None`. We can pass `template_bytes=...`

@pytest.fixture
def mock_s3_get_bytes(monkeypatch):
    from src.shared.storage import object_store

    def mock_get(key):
        with open(key, "rb") as f:
            return f.read()

    monkeypatch.setattr(object_store, "get_bytes", mock_get)

def test_visual_pipeline_taxation(mock_s3_get_bytes):
    filepath = "SampleData/templates/UK Taxation.docx"
    if not os.path.exists(filepath):
        pytest.skip(f"{filepath} not found")

    os.environ["TEMPLATE_ANALYSIS_PIPELINE"] = "visual_v1"
    res = run_template_analysis("t1", "UK Taxation", filepath)
    manifest = res.data

    fields = {f["name"]: f for f in manifest["fields"]}

    assert "candidate_id" in fields
    assert fields["candidate_id"]["template_evidence"]["region_type"] == "label_value_table"
    assert fields["candidate_name"]["template_evidence"]["region_type"] == "label_value_table"

    assert "professional_qualifications" in fields
    prof = fields["professional_qualifications"]
    assert prof["field_type"] == "array_object"
    assert prof["render_contract"]["render_strategy"] == "mailmerge_table_region"
    assert prof["render_contract"]["region_name"].lower() == "bchecktype"
    assert any(sf["name"] == "check_type" for sf in prof["sub_fields"])
    assert "check_type" not in fields

    # Own CV
    debug = manifest.get("debug", {})
    regions = debug.get("visual_regions", []) # Wait, graph doesn't put regions in debug by default unless we add it
    pass

def test_visual_pipeline_london(mock_s3_get_bytes):
    filepath = "SampleData/templates/UK Worldwide London.docx"
    if not os.path.exists(filepath):
        pytest.skip(f"{filepath} not found")

    os.environ["TEMPLATE_ANALYSIS_PIPELINE"] = "visual_v1"
    res = run_template_analysis("t2", "UK Worldwide London", filepath)
    manifest = res.data

    fields = {f["name"]: f for f in manifest["fields"]}
    assert "work_experience" in fields
    assert fields["work_experience"]["field_type"] == "array_object"

    assert "education" in fields
    assert fields["education"]["field_type"] == "array_object"
