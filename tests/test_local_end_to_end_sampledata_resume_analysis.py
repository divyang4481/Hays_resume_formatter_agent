from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.shared.extractor import extract_text_from_bytes
from src.worker.agentic_core import AgenticCore
from src.worker.agents.template_analysis.graph import run_template_analysis


def _field_map(fields: list[dict]) -> dict[str, dict]:
    return {str(field.get("name") or ""): field for field in fields if field.get("name")}


TEMPLATES_DIR = Path("SampleData/templates")
RESUME_PATH = Path("SampleData/orginal_data/Divyang_Panchasara-2026.pdf")
UK_TEMPLATE_PATHS = sorted(TEMPLATES_DIR.glob("UK*.docx"))


@pytest.mark.parametrize("template_path", UK_TEMPLATE_PATHS, ids=lambda p: p.stem)
def test_local_end_to_end_resume_analysis_with_real_resume_data(template_path: Path) -> None:
    resume_path = RESUME_PATH

    assert template_path.is_file(), "Expected sample template file"
    assert resume_path.is_file(), "Expected sample resume file"

    manifest = run_template_analysis(
        template_id=f"local-e2e-{template_path.stem.lower().replace(' ', '-')}",
        template_name=template_path.name,
        template_object_key="",
        template_bytes=template_path.read_bytes(),
    ).data

    fields = manifest.get("fields", [])
    fields_by_name = _field_map(fields)
    assert fields_by_name, "Expected manifest fields from template analysis"

    resume_text = extract_text_from_bytes(resume_path.read_bytes(), filename=resume_path.name)
    assert resume_text.strip(), "Expected extracted resume text"

    agentic_core = AgenticCore()

    resume_fact_fields = [
        field
        for field in fields
        if str(field.get("source_classification") or "resume_fact").strip().lower() == "resume_fact"
    ]

    resume_fact_result = agentic_core.extract_resume_fields(
        fields=resume_fact_fields,
        resume_text=resume_text,
        use_strong_model=True,
    )
    field_mappings = dict((resume_fact_result or {}).get("field_mappings", {}) or {})

    expected_resume_fact_names = {
        str(field.get("name") or "")
        for field in resume_fact_fields
        if str(field.get("name") or "")
    }
    assert expected_resume_fact_names, "Expected at least one resume_fact field"
    assert expected_resume_fact_names.issubset(field_mappings.keys())

    work_experience = (field_mappings.get("work_experience") or {}).get("value")
    if "work_experience" in fields_by_name:
        assert isinstance(work_experience, list)
        assert work_experience, f"Expected work_experience entries for {template_path.name}"
        assert isinstance(work_experience[0], dict)

    education = (field_mappings.get("education") or {}).get("value")
    if "education" in fields_by_name:
        assert isinstance(education, list)
        assert education, f"Expected education entries for {template_path.name}"
        assert isinstance(education[0], dict)

    candidate_name = (field_mappings.get("candidate_name") or {}).get("value")
    if "candidate_name" in fields_by_name:
        assert candidate_name, f"Expected candidate_name to be extracted for {template_path.name}"
