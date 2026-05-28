from src.worker.agents.template_analysis.field_candidate_builder import build_field_candidates_from_evidence
from src.worker.agents.template_analysis.logical_field_grouper import group_logical_fields_from_candidates


def test_grouped_sections_include_sub_fields_for_work_and_education():
    blocks = [
        {"block_id": "b1", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Job description, Date]", "raw_token": "[Job description, Date]"},
        {"block_id": "b1b", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Job description, Date]", "raw_token": "[Job description, Date]"},
        {"block_id": "b2", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Organisation]", "raw_token": "[Organisation]"},
        {"block_id": "b2b", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Organisation]", "raw_token": "[Organisation]"},
        {"block_id": "b3", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Bullet point responsibilities]", "raw_token": "[Bullet point responsibilities]"},
        {"block_id": "b3b", "section_heading": "WORK EXPERIENCE", "placeholder_text": "[Bullet point responsibilities]", "raw_token": "[Bullet point responsibilities]"},
        {"block_id": "b4", "section_heading": "EDUCATION", "placeholder_text": "[Institution, Date]", "raw_token": "[Institution, Date]"},
        {"block_id": "b5", "section_heading": "EDUCATION", "placeholder_text": "[Bullet point grades]", "raw_token": "[Bullet point grades]"},
    ]
    layout = {"canonical_blocks": blocks}
    candidates = build_field_candidates_from_evidence(layout)
    grouped = group_logical_fields_from_candidates(candidates, layout)
    work = next(f for f in grouped if f["name"] == "work_experience")
    edu = next(f for f in grouped if f["name"] == "education")
    assert work["field_type"] == "array_object"
    assert {s["name"] for s in work["sub_fields"]} >= {"job_description_date", "organisation", "bullet_point_responsibilities"}
    assert edu["field_type"] == "array_object"
    assert {s["name"] for s in edu["sub_fields"]} >= {"institution_date", "bullet_point_grades"}
