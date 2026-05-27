from src.worker.agents.template_analysis.graph import _build_grouped_section_fields


def test_grouped_sections_include_sub_fields_for_work_and_education():
    blocks = [
        {"block_id": "b1", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Job description, Date]", "raw_token": "[Job description, Date]"},
        {"block_id": "b2", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Organisation]", "raw_token": "[Organisation]"},
        {"block_id": "b3", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Bullet point responsibilities]", "raw_token": "[Bullet point responsibilities]"},
        {"block_id": "b4", "section_heading": "EDUCATION", "placeholder_text": "[Institution, Date]", "raw_token": "[Institution, Date]"},
        {"block_id": "b5", "section_heading": "EDUCATION", "placeholder_text": "[Bullet point grades]", "raw_token": "[Bullet point grades]"},
    ]
    grouped = _build_grouped_section_fields(blocks)
    work = next(f for f in grouped if f["name"] == "work_experience")
    edu = next(f for f in grouped if f["name"] == "education")
    assert work["field_type"] == "array_object"
    assert {s["name"] for s in work["sub_fields"]} >= {"job_description_date", "organisation", "responsibilities"}
    assert edu["field_type"] == "array_object"
    assert {s["name"] for s in edu["sub_fields"]} >= {"institution_date", "grades"}
