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
    b_item = next(item for item in payload["placeholder_values"] if item["token"] == "[B]")
    assert b_item["value"] == ["y"]
    assert payload["repeat_blocks"]["c"][0]["k"] == "v"


def test_payload_uses_sub_field_value_when_parent_missing():
    manifest = {
        "fields": [
            {
                "name": "professional_qualifications",
                "field_type": "scalar",
                "template_token": "[Qualifications]",
                "sub_fields": [{"name": "qualification_name"}],
                "render_contract": {"render_strategy": "placeholder_replace", "anchor_token": "[Qualifications]"},
            }
        ]
    }
    mapping = {"field_mappings": {"qualification_name": {"value": "PMP"}}}

    payload = build_filled_template_payload(manifest, mapping)
    q_item = next(item for item in payload["placeholder_values"] if item["name"] == "professional_qualifications")
    assert q_item["value"] == "PMP"


def test_payload_builds_array_object_from_sub_fields_when_parent_missing():
    manifest = {
        "fields": [
            {
                "name": "work_experience",
                "field_type": "array_object",
                "sub_fields": [{"name": "job_title"}, {"name": "organisation"}],
                "render_contract": {"render_strategy": "repeat_block", "anchor_token": "[Work]"},
            }
        ]
    }
    mapping = {
        "field_mappings": {
            "job_title": {"value": ["Engineer", "Senior Engineer"]},
            "organisation": {"value": ["Acme", "Globex"]},
        }
    }

    payload = build_filled_template_payload(manifest, mapping)
    assert payload["repeat_blocks"]["work_experience"] == [
        {"job_title": "Engineer", "organisation": "Acme"},
        {"job_title": "Senior Engineer", "organisation": "Globex"},
    ]
