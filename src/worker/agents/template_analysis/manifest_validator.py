from __future__ import annotations

from typing import Any


def validate_manifest_fields_against_layout(fields: list[dict], layout: dict) -> list[dict]:
    blocks = {b.get("block_id"): b for b in layout.get("blocks", [])}
    valid: list[dict[str, Any]] = []
    used_blocks: dict[str, str] = {}

    for field in fields:
        source_ids = field.get("source_block_ids") or []
        if not source_ids:
            continue
        if any(bid not in blocks for bid in source_ids):
            continue

        if field.get("name") == "candidate_own_cv":
            joined = " ".join((blocks[bid].get("evidence_text") or "") for bid in source_ids).lower()
            if not any(x in joined for x in ["candidate's own cv", "candidate cv", "paste candidate cv", "original cv"]):
                continue

        rc = field.get("render_contract") or {}
        token = field.get("template_token") or rc.get("anchor_token") or ""
        for bid in source_ids:
            b = blocks[bid]
            if token and b.get("placeholder_text") and token != b.get("placeholder_text") and not str(token).upper().startswith("MERGEFIELD"):
                continue

            evidence = (b.get("evidence_text") or "").lower()
            section = (b.get("section_heading") or "").lower()
            if "[bullet point list]" in evidence and "interests" not in section:
                # only interests section can carry this placeholder
                continue

            previous = used_blocks.get(bid)
            if previous and previous != field.get("name"):
                continue
            used_blocks[bid] = field.get("name")

        sub_fields = field.get("sub_fields")
        if isinstance(sub_fields, list):
            kept = [sf for sf in sub_fields if sf.get("template_token") and sf.get("name")]
            field["sub_fields"] = kept
            if field.get("field_type") == "array_object" and not kept:
                continue

        valid.append(field)

    return valid
