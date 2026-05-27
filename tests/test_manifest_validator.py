from src.worker.agents.template_analysis.manifest_validator import validate_manifest_fields_against_layout


def test_validator_rejects_candidate_own_cv_without_evidence():
    layout = {"blocks": [{"block_id": "b1", "section_heading": "PROFILE", "evidence_text": "Current salary & benefits [Type text]", "placeholder_text": "[Type text]"}]}
    fields = [{"name": "candidate_own_cv", "template_token": "[Candidate's own CV]", "source_block_ids": ["b1"]}]
    out = validate_manifest_fields_against_layout(fields, layout)
    assert out == []
