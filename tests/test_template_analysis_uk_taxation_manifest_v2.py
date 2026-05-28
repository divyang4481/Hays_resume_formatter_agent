from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from pathlib import Path

from src.worker.agents.template_analysis.graph import run_template_analysis


def test_template_analysis_uk_taxation_section_ownership():
    template = Path("SampleData/templates/UK Taxation.docx")
    data = run_template_analysis("uk-taxation", template.name, "", template.read_bytes()).data
    fields = {f["name"]: f for f in data["fields"]}

    assert fields["key_skills"]["template_evidence"]["section_heading"].lower() == "key skills"

    expected_labels = {
        "notice_period": "Notice period",
        "candidate_town": "Living in",
        "expected_salary": "Salary required",
    }
    for name, label in expected_labels.items():
        ev = fields[name]["template_evidence"]
        assert ev.get("region_type") == "label_value_table"
        assert ev.get("label_text") == label
        assert (ev.get("section_heading") or "").lower() not in {"key skills", "skills"}
        assert ev.get("row_index") is not None
        assert ev.get("cell_index") is not None
