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

        field_name = str(field.get("name") or "").lower()
        if "cv" in field_name:
            joined = " ".join((blocks[bid].get("evidence_text") or "") for bid in source_ids).lower()
            placeholders = " ".join((blocks[bid].get("placeholder_text") or "") for bid in source_ids).lower()
            # For CV-like fields, require explicit placeholder-level CV evidence,
            # not just a nearby heading mention.
            if not any(x in joined for x in ["candidate's own cv", "candidate cv", "paste candidate cv", "original cv"]) or "cv" not in placeholders:
                reject_reason = "hallucinated_candidate_own_cv"
                logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
                continue

        rc = field.get("render_contract") or {}
        token = field.get("template_token") or rc.get("anchor_token") or ""
        placeholder_tokens = {
            str(blocks[bid].get("placeholder_text") or "").strip()
            for bid in source_ids
            if blocks[bid].get("placeholder_text")
        }
        if placeholder_tokens and not str(token).upper().startswith("MERGEFIELD"):
            # Layout evidence is the source of truth. If all blocks agree on the same placeholder,
            # normalize the manifest token and render anchor to that placeholder.
            if len(placeholder_tokens) == 1:
                normalized = next(iter(placeholder_tokens))
                field["template_token"] = normalized
                token = normalized
                rc["anchor_token"] = normalized
                field["render_contract"] = rc
            elif token and token not in placeholder_tokens:
                reject_reason = "token_not_supported_by_source_blocks"
                logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
                continue

        evidence = field.get("template_evidence") or {}
        if not evidence:
            reject_reason = "missing_template_evidence"
            logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
            continue
        evidence.setdefault("section_heading", blocks[source_ids[0]].get("section_heading"))
        evidence.setdefault("label_text", blocks[source_ids[0]].get("label_text"))
        evidence.setdefault("placeholder_text", blocks[source_ids[0]].get("placeholder_text"))
        evidence.setdefault("evidence_text", blocks[source_ids[0]].get("evidence_text"))
        field["template_evidence"] = evidence

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
            # Generic evidence-based pruning: keep only sub-field tokens that are
            # actually evidenced by the parent field source blocks.
            source_placeholders = {
                str(blocks[bid].get("placeholder_text") or "").strip().lower()
                for bid in source_ids
                if blocks[bid].get("placeholder_text")
            }
            if source_placeholders:
                kept = [
                    sf
                    for sf in kept
                    if str(sf.get("template_token") or "").strip().lower() in source_placeholders
                ]
            field["sub_fields"] = kept
            if field.get("field_type") == "array_object" and not kept:
                reject_reason = "array_object_without_sub_fields"
                logger.info("Rejecting field %s: %s", field.get("name"), reject_reason)
                continue

        valid.append(field)

    return valid
