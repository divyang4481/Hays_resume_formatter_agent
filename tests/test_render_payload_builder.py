from src.worker.agents.resume_formatter.render_payload_builder import build_filled_template_payload

def test_payload_separates_channels():
    manifest = {"fields": [
        {"name": "a", "field_type": "scalar", "render_contract": {"render_strategy": "mergefield_replace", "anchor_token": "MERGEFIELD A"}},
        {"name": "b", "field_type": "array", "render_contract": {"render_strategy": "placeholder_replace", "anchor_token": "[B]"}},
        {"name": "c", "field_type": "array_object", "render_contract": {"render_strategy": "repeat_block", "anchor_token": "[C]"}},
    ]}
    mapping = {"field_mappings": {"a": {"value": "x"}, "b": {"value": ["y"]}, "c": {"value": [{"k": "v"}]}}}
    payload = build_filled_template_payload(manifest, mapping)
    assert payload["render_values"]["MERGEFIELD A"] == "x"
    assert payload["placeholder_values"]["[B]"] == ["y"]
    assert payload["repeat_blocks"]["c"][0]["k"] == "v"
