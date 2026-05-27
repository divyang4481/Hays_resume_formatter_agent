from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def validate_manifest_fields_against_layout(fields: list[dict], layout: dict) -> list[dict]:
    blocks = {b.get("block_id"): b for b in layout.get("blocks", [])}
    valid: list[dict[str, Any]] = []
    used_blocks: dict[str, str] = {}

    for field in fields:
        reject_reason: str | None = None
        source_ids = field.get("source_block_ids") or []
        if not source_ids:
            reject_reason = "missing_source_block_ids"
            logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
            continue
        if any(bid not in blocks for bid in source_ids):
            reject_reason = "unknown_source_block_id"
            logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
            continue

        if field.get("name") == "candidate_own_cv":
            joined = " ".join((blocks[bid].get("evidence_text") or "") for bid in source_ids).lower()
            if not any(x in joined for x in ["candidate's own cv", "candidate cv", "paste candidate cv", "original cv"]):
                reject_reason = "hallucinated_candidate_own_cv"
                logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
                continue

        rc = field.get("render_contract") or {}
        token = field.get("template_token") or rc.get("anchor_token") or ""
        field_invalid = False
        for bid in source_ids:
            b = blocks[bid]
            if token and b.get("placeholder_text") and token != b.get("placeholder_text") and not str(token).upper().startswith("MERGEFIELD"):
                field_invalid = True
                reject_reason = "token_not_supported_by_source_block"
                break

            evidence = (b.get("evidence_text") or "").lower()
            section = (b.get("section_heading") or "").lower()
            if "[bullet point list]" in evidence and "interests" not in section:
                # only interests section can carry this placeholder
                field_invalid = True
                reject_reason = "bullet_point_list_wrong_section"
                break

            previous = used_blocks.get(bid)
            if previous and previous != field.get("name"):
                field_invalid = True
                reject_reason = "source_block_reused_for_unrelated_field"
                break
            used_blocks[bid] = field.get("name")

        if field_invalid:
            logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
            continue

        sub_fields = field.get("sub_fields")
        if isinstance(sub_fields, list):
            kept = [sf for sf in sub_fields if sf.get("template_token") and sf.get("name")]
            field["sub_fields"] = kept
            if field.get("field_type") == "array_object" and not kept:
                reject_reason = "array_object_without_sub_fields"
                logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
                continue

        valid.append(field)

    return valid
