from pathlib import Path
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))

from pathlib import Path

from src.worker.agents.template_analysis.graph import run_template_analysis
from src.worker.agents.resume_formatter.render_payload_builder import build_filled_template_payload


def test_resume_format_uk_template_manifest_v2_smoke():
    template = Path("SampleData/templates/UK Worldwide London.docx")
    manifest = run_template_analysis("uk-worldwide", template.name, "", template.read_bytes()).data
    payload = build_filled_template_payload(manifest, {"field_mappings": {"candidate_name": {"value": "Jane Doe"}, "key_skills": {"value": ["Python"]}}})
    assert payload is not None
    assert payload.get("placeholder_values") is not None or payload.get("render_values") is not None
