from pathlib import Path

import pytest

from src.worker.agents.template_analysis.graph import run_template_analysis

TEMPLATES = [
    "UK Worldwide London.docx",
    "UK Treasury.docx",
    "UK Taxation.docx",
]


@pytest.mark.parametrize("template_name", TEMPLATES)
def test_multi_template_manifest_v2(template_name: str):
    template = Path("SampleData/templates", template_name)
    data = run_template_analysis("uk", template.name, "", template.read_bytes()).data
    assert data["version"] == 2
    assert data["manifest_schema"] == "template_manifest_v2"
    assert data["debug"]["critic"]["passed"] is True
    assert all(f["source_block_ids"] for f in data["fields"])
    assert all(f["template_evidence"] for f in data["fields"])

    field_names = {f["name"] for f in data["fields"]}
    if template_name == "UK Worldwide London.docx":
        assert "work_experience" in field_names
        assert "education" in field_names
        assert "interests_and_activities" in field_names
        assert "candidate_name" in field_names
        assert "presenter_name" in field_names
        assert "candidatefullname" not in field_names
    else:
        assert "candidate_name" in field_names
        assert "candidate_id" in field_names
        assert "candidate_town" in field_names
        assert "expected_salary" in field_names
        assert "presenter_name" in field_names
        assert "work_experience" not in field_names
        assert "education" not in field_names
