from __future__ import annotations

from typing import Any

from src.shared.manifest_models import FilledTemplatePayload, adapt_v1_field_to_v2


def build_filled_template_payload(
    manifest: dict,
    mapping_result: dict,
    recruiter_input: dict | None = None,
    ats_input: dict | None = None,
) -> dict:
    recruiter_input = recruiter_input or {}
    ats_input = ats_input or {}
    payload = FilledTemplatePayload(
        template_id=manifest.get("template_id"),
        manifest_id=manifest.get("manifest_id"),
    )

    fields = manifest.get("fields", [])
    mappings = mapping_result.get("field_mappings", {})

    for raw_field in fields:
        field = raw_field if "render_contract" in raw_field else adapt_v1_field_to_v2(raw_field)
        name = field["name"]
        source_classification = field.get("source_classification", "resume_fact")
        required = bool(field.get("required", False))
        render_strategy = field.get("render_contract", {}).get("render_strategy", "placeholder_replace")

        mapped_value: Any = None
        if source_classification in ("input_only", "recruiter_input"):
            mapped_value = recruiter_input.get(name)
        elif source_classification == "ats_input":
            mapped_value = ats_input.get(name)
        else:
            mapped_value = (mappings.get(name) or {}).get("value")

        if (mapped_value is None or mapped_value == [] or mapped_value == "") and required and source_classification in (
            "input_only",
            "recruiter_input",
            "ats_input",
        ):
            payload.missing_fields_requiring_recruiter_or_ats_input.append(name)
            continue

        token = field.get("template_token") or field.get("render_contract", {}).get("anchor_token") or name
        if render_strategy == "mergefield_replace":
            payload.render_values[token] = mapped_value
        elif render_strategy in ("placeholder_replace", "bullet_list_replace", "copy_paste_block"):
            payload.placeholder_values[token] = mapped_value
        elif render_strategy == "repeat_block":
            payload.repeat_blocks[name] = mapped_value or []
        else:
            payload.placeholder_values[token] = mapped_value

    return payload.model_dump()
