from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

import json
from pathlib import Path

from src.worker.agents.template_analysis.graph import run_template_analysis


def find_field(fields, name):
    return next(f for f in fields if f["name"] == name)


def test_template_analysis_uk_worldwide_manifest_v2():
    template = Path("SampleData/templates/UK Worldwide London.docx")
    data = run_template_analysis("uk-worldwide", template.name, "", template.read_bytes()).data
    assert data["version"] == 2
    assert data["manifest_schema"] == "template_manifest_v2"
    fields = data["fields"]
    field_names = {f["name"] for f in fields}
    assert len(field_names) == len(fields)
    assert "work_experience" in field_names
    assert "education" in field_names
    assert "candidatefullname" in field_names
    assert "candidateid" in field_names
    assert "noticeperiod" in field_names
    assert "employeename" in field_names
    assert "employeejobtitle" in field_names
    assert "employeespecialistarea" in field_names
    assert "employeetelno" in field_names
    assert "employeeemail" in field_names
    assert "our_expert_opinion" in field_names
    assert "candidate_own_cv" not in field_names
    assert "interests_and_activities" in field_names

    work = find_field(fields, "work_experience")
    assert work["field_type"] == "array_object"
    assert len(work["sub_fields"]) == 3
    assert work["render_contract"]["render_strategy"] == "repeat_block"

    education = find_field(fields, "education")
    assert education["field_type"] == "array_object"
    assert education["render_contract"]["render_strategy"] == "repeat_block"

    critic = data["debug"]["critic"]
    assert critic["passed"] is True
    assert critic["score"] >= 0.90
    for f in fields:
        assert f["source_block_ids"]
        assert f["template_evidence"]
        assert f["render_contract"]
