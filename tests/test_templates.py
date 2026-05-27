from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import pytest

from src.worker.agents.template_analysis.graph import (
    _extract_template_tokens,
    _extract_template_text,
    _field_has_evidence,
    run_template_analysis,
)
from src.worker.agents.template_analysis.xml_parser import extract_fields_from_docx

TEMPLATES_DIR = Path("SampleData/templates")


def test_templates_exist():
    assert TEMPLATES_DIR.exists()
    assert list(TEMPLATES_DIR.glob("*.docx"))


@pytest.mark.parametrize("template_path", list(Path("SampleData/templates").glob("*.docx")))
def test_extract_tokens_and_text(template_path: Path):
    docx_bytes = template_path.read_bytes()
    tokens = _extract_template_tokens(docx_bytes)
    assert isinstance(tokens, list)
    text = _extract_template_text(docx_bytes)
    assert isinstance(text, str)


@patch("src.shared.storage.object_store.get_bytes")
@patch("src.worker.agentic_core.AgenticCore.infer_template_manifest_fields")
def test_generate_field_manifest_mocked(mock_infer, mock_get_bytes):
    template_path = TEMPLATES_DIR / "UK Taxation.docx"
    docx_bytes = template_path.read_bytes()
    mock_get_bytes.return_value = docx_bytes

    detected_tokens = _extract_template_tokens(docx_bytes)
    mock_infer.return_value = [
        {
            "name": name,
            "field_type": "scalar",
            "source_hint": f"Extract the {name}",
            "template_token": token,
            "required": False,
            "formatting_hint": "plain_text",
        }
        for name, token in detected_tokens[:3]
    ]

    result = run_template_analysis(
        template_id="test-template-id",
        template_name=template_path.name,
        template_object_key=f"templates/{template_path.name}",
    )

    assert result.status.value == "completed"
    assert "fields" in result.data
    assert len(result.data["fields"]) > 0


def test_xml_parser_disambiguates_generic_placeholders_using_context():
    template_path = TEMPLATES_DIR / "UK Worldwide London.docx"
    fields = extract_fields_from_docx(template_path)

    names = {f["name"] for f in fields}
    tokens = [f["token"].lower() for f in fields]

    # Specific merge fields should be detected from XML.
    assert "candidatefullname" in names
    assert "candidateid" in names
    assert "noticeperiod" in names

    # Generic placeholders must be context-disambiguated (not a raw shared name).
    assert "type_text" not in names
    assert any(name.startswith("skills_item") for name in names)
    assert any(name.startswith("job_description_date") for name in names)
    assert any(name.startswith("organisation") for name in names)

    # Bullet contexts should be inferred as array-like item fields.
    assert any(name.startswith("bullet_point_responsibilities_item") for name in names)

    # We should keep macrobutton/mergefield evidence in tokens.
    assert any("macrobutton" in t for t in tokens)
    assert any("mergefield" in t for t in tokens)


def test_field_evidence_filtering_requires_token_or_text_match():
    template_text = "skills [Type text]"
    token_values = {"[Type text]"}
    fields = [
        {"name": "skills", "template_token": "[Type text]", "injection_details": {"placeholder_text": "[Type text]"}},
        {"name": "candidate_own_cv", "template_token": "[Candidate's own CV]", "injection_details": {"placeholder_text": "[Candidate's own CV]"}},
    ]

    filtered = [f for f in fields if _field_has_evidence(f, template_text.lower(), token_values)]
    names = {f["name"] for f in filtered}
    assert "skills" in names
    assert "candidate_own_cv" not in names
