import re
from typing import Any

from src.shared.manifest_models import FilledTemplatePayload, adapt_v1_field_to_v2


def clean_spaced_text(text: str) -> str:
    """Normalize text where characters are separated by single spaces, keeping words separated."""
    if len(text) > 5 and text.count(" ") / len(text) > 0.3:
        # replace double/triple spaces with a special marker
        temp = re.sub(r"\s{2,}", " | ", text)
        # remove single spaces
        temp = temp.replace(" ", "")
        # restore double spaces as a single space
        return temp.replace("|", " ").strip()
    return text


def _extract_fallback_position(cv_text: str | None) -> str | None:
    """Parse candidate CV text to find the most likely current position or job title."""
    if not cv_text:
        return None
    lines = [line.strip() for line in cv_text.splitlines() if line.strip()]
    if not lines:
        return None
        
    title_keywords = [
        "architect", "consultant", "engineer", "developer", "manager", "analyst", 
        "lead", "specialist", "director", "designer", "support", "writer", "officer",
        "administrator", "expert", "strategist", "head", "executive"
    ]
    
    # Try looking at the first 4 lines (skipping the name)
    for line in lines[1:4]:
        # Normalize and clean spaced text first
        cleaned = clean_spaced_text(line)
        normalized_line = re.sub(r"\s+", " ", cleaned)
        if any(kw in normalized_line.lower() for kw in title_keywords) and len(normalized_line) < 60:
            return normalized_line

    # Try searching for commas or 'at' indicating position
    for line in lines:
        cleaned = clean_spaced_text(line)
        if "," in cleaned or " at " in cleaned or " - " in cleaned:
            parts = [p.strip() for p in re.split(r",| at | - ", cleaned)]
            if parts:
                first_part = parts[0]
                if any(kw in first_part.lower() for kw in title_keywords) and len(first_part) < 50:
                    return first_part

    return None


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
    placeholder_items: list[dict[str, Any]] = []

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
            if not mapped_value:
                mapped_value = (mappings.get(name) or {}).get("value")
            if not mapped_value and name == "position_required":
                cv_text = (mappings.get("candidate_own_cv") or {}).get("value")
                mapped_value = _extract_fallback_position(cv_text) or \
                               (mappings.get("current_position") or {}).get("value") or \
                               (mappings.get("job_title") or {}).get("value")
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
            payload.render_values[name] = mapped_value
        elif render_strategy in ("placeholder_replace", "bullet_list_replace", "copy_paste_block"):
            placeholder_items.append({
                "name": name,
                "token": token,
                "value": mapped_value,
                "source_block_id": (field.get("source_block_ids") or [None])[0],
                "occurrence_selector": field.get("render_contract", {}).get("occurrence_selector") or field.get("occurrence_selector") or {},
            })
        elif render_strategy == "repeat_block":
            payload.repeat_blocks[name] = mapped_value or []
        else:
            placeholder_items.append({"name": name, "token": token, "value": mapped_value})

    payload.placeholder_values = placeholder_items
    return payload.model_dump()
