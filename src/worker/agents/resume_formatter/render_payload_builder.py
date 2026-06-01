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


def _is_position_like_field(field: dict[str, Any]) -> bool:
    semantic = _field_semantic_text(field)
    return any(term in semantic for term in ("position", "job title", "title", "role", "designation"))


def _field_semantic_text(field: dict[str, Any]) -> str:
    parts = [
        str(field.get(k) or "")
        for k in ("name", "display_label", "source_hint", "template_token")
    ]
    for sub_field in (field.get("sub_fields") or []):
        if not isinstance(sub_field, dict):
            continue
        parts.extend(
            str(sub_field.get(k) or "")
            for k in ("name", "display_label", "source_hint", "template_token")
        )
    return " ".join(parts).lower()


def _extract_resume_blob_from_mappings(mappings: dict[str, Any]) -> str | None:
    for key, entry in mappings.items():
        value = (entry or {}).get("value")
        if not isinstance(value, str):
            continue
        key_text = str(key or "").lower()
        if any(marker in key_text for marker in ("cv", "resume", "original")) and len(value) > 120:
            return value

    for entry in mappings.values():
        value = (entry or {}).get("value")
        if isinstance(value, str) and ("\n" in value or "\r" in value) and len(value) > 200:
            return value
    return None


def _extract_semantic_scalar_from_mappings(mappings: dict[str, Any], terms: tuple[str, ...]) -> str | None:
    for key, entry in mappings.items():
        key_text = str(key or "").lower()
        if not any(term in key_text for term in terms):
            continue
        value = (entry or {}).get("value")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_mapping_with_sub_fields(field: dict[str, Any], mappings: dict[str, Any]) -> Any:
    name = str(field.get("name") or "").strip()
    if not name:
        return None

    direct_value = (mappings.get(name) or {}).get("value")
    if direct_value not in (None, "", []):
        return direct_value

    sub_fields = field.get("sub_fields") or []
    if not isinstance(sub_fields, list) or not sub_fields:
        return direct_value

    sub_values: dict[str, Any] = {}
    for sub_field in sub_fields:
        if not isinstance(sub_field, dict):
            continue
        sub_name = str(sub_field.get("name") or "").strip()
        if not sub_name:
            continue
        sub_value = (mappings.get(sub_name) or {}).get("value")
        if sub_value in (None, "", []):
            continue
        sub_values[sub_name] = sub_value

    if not sub_values:
        return direct_value

    field_type = str(field.get("field_type") or "scalar").lower()
    if field_type == "array_object":
        max_len = max((len(v) for v in sub_values.values() if isinstance(v, list)), default=0)
        if max_len > 0:
            rows: list[dict[str, Any]] = []
            for idx in range(max_len):
                row: dict[str, Any] = {}
                for sub_name, sub_value in sub_values.items():
                    if isinstance(sub_value, list):
                        if idx < len(sub_value):
                            row[sub_name] = sub_value[idx]
                    else:
                        row[sub_name] = sub_value
                if row:
                    rows.append(row)
            return rows
        return [sub_values]

    if field_type == "array":
        for sub_value in sub_values.values():
            if isinstance(sub_value, list):
                return sub_value
        return list(sub_values.values())

    for sub_value in sub_values.values():
        if isinstance(sub_value, list):
            if sub_value:
                return sub_value[0]
            continue
        return sub_value
    return direct_value


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
            if not mapped_value and _is_position_like_field(field):
                cv_text = _extract_resume_blob_from_mappings(mappings)
                mapped_value = _extract_fallback_position(cv_text) or _extract_semantic_scalar_from_mappings(
                    mappings,
                    ("position", "title", "role", "designation"),
                )
        elif source_classification == "ats_input":
            mapped_value = ats_input.get(name)
        else:
            mapped_value = _resolve_mapping_with_sub_fields(field, mappings)

        if (mapped_value is None or mapped_value == [] or mapped_value == "") and source_classification in (
            "input_only",
            "recruiter_input",
            "ats_input",
        ):
            if name not in payload.missing_fields_requiring_recruiter_or_ats_input:
                payload.missing_fields_requiring_recruiter_or_ats_input.append(name)
            if required:
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
