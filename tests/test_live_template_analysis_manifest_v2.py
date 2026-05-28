import json
from pathlib import Path
import pytest
from src.worker.agents.template_analysis.graph import run_template_analysis

def test_live_template_analysis_manifest_v2_hays(monkeypatch):
    template_path = Path("SampleData/templates/UK Worldwide London.docx")
    assert template_path.is_file(), "Hays template file not found"
    
    # Run the live template analysis locally using our v2 layout pipeline
    result = run_template_analysis(
        template_id="test-hays-live-id",
        template_name=template_path.name,
        template_object_key=f"templates/{template_path.name}",
        template_bytes=template_path.read_bytes()
    )
    
    assert result.status.value == "completed"
    manifest = result.data
    
    # Assertions for schema version and type
    assert manifest["version"] == 2
    assert manifest["manifest_schema"] == "template_manifest_v2"
    
    # Assert that debug section is present in local non-production runs
    assert "debug" in manifest
    assert manifest["debug"]["pipeline_version"] == "layout_v2_agentic_qc_2026_05_28"
    assert manifest["debug"]["blocks_count"] > 0
    assert manifest["debug"]["fields_count"] > 0
    
    field_names = {f["name"] for f in manifest["fields"]}
    
    # Verify strict golden rule field exclusions
    assert "candidate_own_cv" not in field_names
    
    # Verify presence of all expected logical fields
    expected_fields = [
        "candidate_name",
        "candidate_id",
        "our_expert_opinion",
        "current_salary_benefits",
        "salary_required",
        "notice_period",
        "professional_qualifications",
        "skills",
        "current_position",
        "work_experience",
        "education",
        "interests_and_activities",
        "presenter_name",
        "presenter_title",
        "presenter_specialist_area",
        "presenter_phone",
        "presenter_email"
    ]
    
    for field in expected_fields:
        assert field in field_names, f"Expected field '{field}' not found in manifest"

    # Verify bullet lists and groups are cleanly separated and don't include [Bullet point list] text
    work = next(f for f in manifest["fields"] if f["name"] == "work_experience")
    assert "[Bullet point list]" not in json.dumps(work)
    
    edu = next(f for f in manifest["fields"] if f["name"] == "education")
    assert "[Bullet point list]" not in json.dumps(edu)


def test_live_template_analysis_manifest_v2_taxation():
    template_path = Path("SampleData/templates/UK Taxation.docx")
    assert template_path.is_file(), "Taxation template file not found"
    
    # Run the live template analysis locally using our v2 layout pipeline
    result = run_template_analysis(
        template_id="test-taxation-live-id",
        template_name=template_path.name,
        template_object_key=f"templates/{template_path.name}",
        template_bytes=template_path.read_bytes()
    )
    
    assert result.status.value == "completed"
    manifest = result.data
    
    # Assertions for schema version and type
    assert manifest["version"] == 2
    assert manifest["manifest_schema"] == "template_manifest_v2"
    
    # Assert that debug section is present in local non-production runs
    assert "debug" in manifest
    assert manifest["debug"]["pipeline_version"] == "layout_v2_agentic_qc_2026_05_28"
    assert manifest["debug"]["blocks_count"] > 0
    assert manifest["debug"]["fields_count"] > 0
    
    field_names = {f["name"] for f in manifest["fields"]}
    
    # Verify presence of all expected logical fields for Taxation
    expected_fields = [
        "candidate_id",
        "candidate_name",
        "check_type",
        "key_skills",
        "notice_period",
        "candidate_town",
        "expected_salary",
        "presenter_name",
        "presenter_title",
        "presenter_specialist_area",
        "presenter_phone",
        "presenter_email"
    ]
    
    for field in expected_fields:
        assert field in field_names, f"Expected field '{field}' not found in manifest"


def test_live_template_analysis_manifest_v2_treasury():
    template_path = Path("SampleData/templates/UK Treasury.docx")
    assert template_path.is_file(), "Treasury template file not found"
    
    # Run the live template analysis locally using our v2 layout pipeline
    result = run_template_analysis(
        template_id="test-treasury-live-id",
        template_name=template_path.name,
        template_object_key=f"templates/{template_path.name}",
        template_bytes=template_path.read_bytes()
    )
    
    assert result.status.value == "completed"
    manifest = result.data
    
    # Assertions for schema version and type
    assert manifest["version"] == 2
    assert manifest["manifest_schema"] == "template_manifest_v2"
    
    # Assert that debug section is present in local non-production runs
    assert "debug" in manifest
    assert manifest["debug"]["pipeline_version"] == "layout_v2_agentic_qc_2026_05_28"
    assert manifest["debug"]["blocks_count"] > 0
    assert manifest["debug"]["fields_count"] > 0
    
    field_names = {f["name"] for f in manifest["fields"]}
    
    # Verify presence of all expected logical fields for Treasury
    expected_fields = [
        "candidate_id",
        "candidate_name",
        "check_type",
        "key_skills",
        "notice_period",
        "candidate_town",
        "expected_salary",
        "presenter_name",
        "presenter_title",
        "presenter_specialist_area",
        "presenter_phone",
        "presenter_email"
    ]
    
    for field in expected_fields:
        assert field in field_names, f"Expected field '{field}' not found in manifest"
