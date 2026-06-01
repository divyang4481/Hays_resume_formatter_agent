from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

import json
from src.worker.agents.template_analysis.logical_field_grouper import group_logical_fields_from_candidates


def mk(name, token, bid, section, ftype="scalar"):
    return {"suggested_name": name, "display_label": name.title(), "field_type": ftype, "template_token": token, "source_block_ids": [bid], "template_evidence": {"section_heading": section, "label_text": name.title(), "placeholder_text": token}, "render_contract": {"render_strategy": "placeholder_replace", "anchor_token": token, "occurrence_selector": {"source_block_id": bid}}}


def find_field(fields, name):
    return next(f for f in fields if f["name"] == name)


def test_groups_skills_repeated_type_text_blocks():
    fields=[mk("skills","[Type text]",f"b00{i}","Skills","array") for i in range(8,11)]
    out=group_logical_fields_from_candidates(fields,{})
    field_names=[f['name'] for f in out]
    assert "skills" in field_names
    skills=find_field(out, "skills")
    assert skills["field_type"] == "array"
    assert len(skills["source_block_ids"]) == 3
    assert skills["render_contract"]["render_strategy"] in {"placeholder_replace", "bullet_list_replace"}


def test_groups_work_experience_repeat_block():
    fields=[]
    for i in range(3):
        fields.append(mk("work_experience","[Job description, Date]",f"b01{i}","WORK EXPERIENCE"))
        fields.append(mk("work_experience","[Organisation]",f"b02{i}","WORK EXPERIENCE"))
        fields.append(mk("work_experience","[Bullet point responsibilities]",f"b03{i}","WORK EXPERIENCE","array"))
    out=group_logical_fields_from_candidates(fields,{})
    work=find_field(out,"work_experience")
    assert work["field_type"] == "array_object"
    assert work["render_contract"]["render_strategy"] == "repeat_block"
    assert len(work["source_block_ids"]) == 9
    assert len(work["sub_fields"]) == 3
    assert "[Bullet point list]" not in json.dumps(work)


def test_groups_education_section():
    fields=[mk("education","[Institution, Date]","b026","EDUCATION"),mk("education","[Bullet point grades]","b027","EDUCATION","array")]
    out=group_logical_fields_from_candidates(fields,{})
    education=find_field(out,"education")
    assert education["field_type"] == "array_object"
    assert len(education["source_block_ids"]) == 2


def test_keeps_interests_as_array():
    out=group_logical_fields_from_candidates([mk("interests","[Bullet point list]","b028","INTERESTS AND ACTIVITIES","array")],{})
    interests=find_field(out,"interests")
    assert interests["field_type"] == "array"
    assert interests["template_token"] == "[Bullet point list]"


def test_does_not_collapse_distinct_labels_with_same_token_in_one_section():
    fields = [
        {
            "name": None,
            "display_label": "Current salary & benefits",
            "field_type": "scalar",
            "template_token": "[Type text]",
            "source_block_ids": ["tbl_000_r_004_c_001"],
            "template_evidence": {
                "section_heading": "CANDIDATE PROFILE",
                "label_text": "Current salary & benefits",
                "region_type": "label_value_table",
            },
        },
        {
            "name": None,
            "display_label": "Professional qualifications",
            "field_type": "scalar",
            "template_token": "[Type text]",
            "source_block_ids": ["tbl_000_r_007_c_001"],
            "template_evidence": {
                "section_heading": "CANDIDATE PROFILE",
                "label_text": "Professional qualifications",
                "region_type": "label_value_table",
            },
        },
    ]

    out = group_logical_fields_from_candidates(fields, {})
    names = {f["name"] for f in out}

    assert "current_salary_benefits" in names
    assert "professional_qualifications" in names
