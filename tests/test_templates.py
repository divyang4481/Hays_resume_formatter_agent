from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from src.worker.agents.template_analysis.graph import (
    _extract_template_tokens,
    _extract_template_text,
    _field_has_evidence,
    _inject_required_hays_fields,
    run_template_analysis
)

TEMPLATES_DIR = Path("SampleData/templates")


def test_templates_exist():
    """Verify that templates directory exists and contains docx files."""
    assert TEMPLATES_DIR.exists()
    docx_files = list(TEMPLATES_DIR.glob("*.docx"))
    assert len(docx_files) > 0, "No docx templates found in SampleData/templates"


@pytest.mark.parametrize("template_path", list(Path("SampleData/templates").glob("*.docx")))
def test_extract_tokens_and_text(template_path: Path):
    """Test that we can successfully extract tokens and text from actual templates."""
    docx_bytes = template_path.read_bytes()
    
    # 1. Extract tokens
    tokens = _extract_template_tokens(docx_bytes)
    assert isinstance(tokens, list)
    
    # 2. Extract preview text
    text = _extract_template_text(docx_bytes)
    assert isinstance(text, str)
    
    # Log information about the templates
    print(f"\nTemplate: {template_path.name}")
    print(f"Extracted {len(tokens)} tokens: {[t[0] for t in tokens]}")
    print(f"Extracted text length: {len(text)}")


@patch("src.shared.storage.object_store.get_bytes")
@patch("src.worker.agentic_core.AgenticCore.infer_template_manifest_fields")
def test_generate_field_manifest_mocked(mock_infer, mock_get_bytes):
    """Verify end-to-end template analysis with mocked LLM response."""
    template_path = TEMPLATES_DIR / "UK Taxation.docx"
    docx_bytes = template_path.read_bytes()
    mock_get_bytes.return_value = docx_bytes
    
    # Mock LLM to return custom fields mapping detected tokens
    detected_tokens = _extract_template_tokens(docx_bytes)
    mock_inferred = []
    for name, token in detected_tokens[:3]:
        mock_inferred.append({
            "name": name,
            "field_type": "scalar",
            "source_hint": f"Extract the {name}",
            "template_token": token,
            "required": False,
            "formatting_hint": "plain_text"
        })
    mock_infer.return_value = mock_inferred

    result = run_template_analysis(
        template_id="test-template-id",
        template_name=template_path.name,
        template_object_key=f"templates/{template_path.name}"
    )

    assert result.status.value == "completed"
    assert "fields" in result.data
    assert len(result.data["fields"]) > 0
    
    # Assert each field has all the contract requirements
    for field in result.data["fields"]:
        assert "name" in field
        assert "field_type" in field
        assert "template_token" in field
        assert "source_hint" in field
        assert "formatting_hint" in field
        assert "required" in field


def test_generate_field_manifest_live():
    """Verify live template analysis calling Bedrock to extract field manifests."""
    template_path = TEMPLATES_DIR / "UK Taxation.docx"
    docx_bytes = template_path.read_bytes()
    
    tokens = _extract_template_tokens(docx_bytes)
    template_text = _extract_template_text(docx_bytes)
    
    llm_tokens = [{"name": name, "template_token": token} for name, token in tokens]
    
    from src.worker.agentic_core import AgenticCore
    agentic_core = AgenticCore()
    
    print("\n--- Starting Live Bedrock Template Analysis ---")
    try:
        inferred = agentic_core.infer_template_manifest_fields(
            template_name=template_path.name,
            tokens=llm_tokens,
            template_text=template_text,
            use_strong_model=False,
        )
        print(f"Live Bedrock extracted {len(inferred)} fields:")
        import json
        print(json.dumps(inferred, indent=2))
        
        assert isinstance(inferred, list)
        assert len(inferred) > 0
        for field in inferred:
            assert "name" in field
            assert "template_token" in field
    except Exception as e:
        pytest.fail(f"Live Bedrock template analysis failed: {e}")


def test_hays_field_postprocessing_drops_hallucination_and_adds_required_fields():
    template_text = """
    Current salary & benefits [Type text]
    Salary required [Type text]
    Notice period <<NoticePeriod>>
    Professional qualifications [Type text]
    Skills [Type text]
    Current position Use bullets if required
    INTERESTS AND ACTIVITIES [Bullet point list]
    """
    token_values = {"[Type text]", "MERGEFIELD NoticePeriod", "[Bullet point list]"}
    fields = [
        {
            "name": "candidate_own_cv",
            "template_token": "[Candidate's own CV]",
            "injection_details": {"placeholder_text": "[Candidate's own CV]"},
        },
        {
            "name": "key_skills",
            "template_token": "[Type text]",
            "injection_details": {"placeholder_text": "[Type text]"},
        },
    ]

    filtered = [f for f in fields if _field_has_evidence(f, template_text.lower(), token_values)]
    filtered = [
        f for f in filtered
        if f.get("name") != "candidate_own_cv"
        or "candidate's own cv" in template_text.lower()
    ]
    final_fields = _inject_required_hays_fields(filtered, template_text)
    names = {f["name"] for f in final_fields}

    assert "candidate_own_cv" not in names
    assert "current_salary_benefits" in names
    assert "salary_required" in names
    assert "notice_period" in names
    assert "professional_qualifications" in names
    assert "current_position" in names
    assert "interests_and_activities" in names
