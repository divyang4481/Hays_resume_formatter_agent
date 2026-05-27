from src.worker.agents.resume_formatter.render_payload_builder import build_filled_template_payload


def test_placeholder_values_list_mode_with_occurrence_selector():
    manifest = {
        "fields": [
            {"name": "current_salary_benefits", "source_classification": "recruiter_input", "template_token": "[Type text]", "source_block_ids": ["b004"], "render_contract": {"render_strategy": "placeholder_replace", "anchor_token": "[Type text]", "occurrence_selector": {"label_text": "Current salary & benefits", "occurrence_index": 1}}}
        ]
    }
    out = build_filled_template_payload(manifest, {"field_mappings": {}}, recruiter_input={"current_salary_benefits": "£65,000"})
    assert isinstance(out["placeholder_values"], list)
    assert out["placeholder_values"][0]["occurrence_selector"]["occurrence_index"] == 1
