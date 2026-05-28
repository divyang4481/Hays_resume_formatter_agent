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
    field_names = [f["name"] for f in fields]
    assert len(field_names) == len(set(field_names))
    assert len(field_names) >= 8
    assert "candidate_own_cv" not in field_names
    assert "interests_and_activities" in field_names
    for f in fields:
        assert f["source_block_ids"]
        assert f["template_evidence"]
        assert f["render_contract"]
