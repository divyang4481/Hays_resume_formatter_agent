from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


def _log_rejection(field: dict, reason: str) -> None:
    logger.info("[ManifestValidator] removed field=%s reason=%s", field.get("name"), reason)


def validate_manifest_fields_against_layout(fields: list[dict], layout: dict) -> list[dict]:
    blocks = {b.get("block_id"): b for b in layout.get("blocks", [])}
    valid: list[dict[str, Any]] = []
    used_blocks: dict[str, str] = {}

    for field in fields:
        reject_reason: str | None = None
        source_ids = field.get("source_block_ids") or []
        if not source_ids:
            reject_reason = "missing_source_block_ids"
            _log_rejection(field, reject_reason)
            continue
        if any(bid not in blocks for bid in source_ids):
            reject_reason = "unknown_source_block_id"
            _log_rejection(field, reject_reason)
            continue

        # Generic anti-hallucination rule for CV-like targets (no field-name hardcoding):
        # if either declared token/anchor indicates CV content, require explicit CV evidence.
        declared_token = str(field.get("template_token") or "").lower()
        declared_anchor = str((field.get("render_contract") or {}).get("anchor_token") or "").lower()
        cv_like_declared = "cv" in declared_token or "cv" in declared_anchor
        if cv_like_declared:
            joined = " ".join((blocks[bid].get("evidence_text") or "") for bid in source_ids).lower()
            placeholders = " ".join((blocks[bid].get("placeholder_text") or "") for bid in source_ids).lower()
            instruction_text = str((field.get("template_evidence") or {}).get("instruction_text") or "").lower()
            # For CV-like fields, require explicit placeholder-level CV evidence or instruction text,
            # not just a nearby heading mention.
            if not any(x in joined for x in ["candidate's own cv", "candidate cv", "paste candidate cv", "original cv"]) and "cv" not in placeholders and not any(x in instruction_text for x in ["candidate's own cv", "candidate cv", "paste candidate cv", "original cv"]):
                reject_reason = "hallucinated_cv_instruction_field"
                _log_rejection(field, reject_reason)
                continue

        rc = field.get("render_contract") or {}
        token = field.get("template_token") or rc.get("anchor_token") or ""
        placeholder_tokens = {
            str(blocks[bid].get("placeholder_text") or "").strip()
            for bid in source_ids
            if blocks[bid].get("placeholder_text")
        }
        if placeholder_tokens and not str(token).upper().startswith("MERGEFIELD") and field.get("field_type") != "array_object":
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
                _log_rejection(field, reject_reason)
                continue

        template_evidence = field.get("template_evidence") or {}
        if not template_evidence:
            reject_reason = "missing_template_evidence"
            _log_rejection(field, reject_reason)
            continue
        template_evidence.setdefault("section_heading", blocks[source_ids[0]].get("section_heading"))
        template_evidence.setdefault("label_text", blocks[source_ids[0]].get("label_text"))
        template_evidence.setdefault("placeholder_text", blocks[source_ids[0]].get("placeholder_text"))
        template_evidence.setdefault("evidence_text", blocks[source_ids[0]].get("evidence_text"))

        template_evidence.setdefault("region_type", blocks[source_ids[0]].get("region_type"))
        template_evidence.setdefault("block_role", blocks[source_ids[0]].get("block_role"))
        template_evidence.setdefault("table_index", blocks[source_ids[0]].get("table_index"))
        template_evidence.setdefault("row_index", blocks[source_ids[0]].get("row_index"))
        template_evidence.setdefault("cell_index", blocks[source_ids[0]].get("cell_index"))
        field["template_evidence"] = template_evidence

        field_invalid = False
        for bid in source_ids:
            b = blocks[bid]
            if token and b.get("placeholder_text") and token != b.get("placeholder_text") and not str(token).upper().startswith("MERGEFIELD") and field.get("field_type") != "array_object":
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
            _log_rejection(field, reject_reason or "field_invalid")
            continue

        if str((field.get("render_contract") or {}).get("render_strategy") or "").strip().lower() == "remove_instruction_text":
            continue
        if bool((field.get("template_evidence") or {}).get("is_instruction_only")):
            continue
        # Generic label-as-token guard: if the token looks like a bracket placeholder,
        # it must exist in source placeholders for this field.
        token_str = str(token).strip()
        if token_str.startswith("[") and token_str.endswith("]") and token_str not in placeholder_tokens:
            continue
        if field.get("field_type") != "array_object" and template_evidence.get("placeholder_text") and field.get("template_token") and template_evidence.get("placeholder_text") != field.get("template_token"):
            continue
        if field.get("template_token") == "[Type text]" and not (rc.get("occurrence_selector") or {}).get("source_block_id"):
            continue
        sub_fields = field.get("sub_fields")
        if isinstance(sub_fields, list):
            kept = [sf for sf in sub_fields if sf.get("template_token") and sf.get("name")]
            if field.get("field_type") == "array_object":
                field["sub_fields"] = kept
                if not kept:
                    reject_reason = "array_object_without_sub_fields"
                    _log_rejection(field, reject_reason)
                    continue
                valid.append(field)
                continue
            # Generic evidence-based pruning: keep only sub-field tokens that are
            # actually evidenced by the parent field source blocks.
            source_placeholders = {
                str(blocks[bid].get("placeholder_text") or "").strip().lower()
                for bid in source_ids
                if blocks[bid].get("placeholder_text")
            }
            placeholder_tokens = {
                str(t).strip().lower()
                for t in (field.get("template_evidence") or {}).get("placeholder_tokens", [])
                if str(t).strip()
            }
            supported_tokens = source_placeholders | placeholder_tokens
            if supported_tokens:
                kept = [
                    sf
                    for sf in kept
                    if str(sf.get("template_token") or "").strip().lower() in supported_tokens
                ]
            field["sub_fields"] = kept
            if field.get("field_type") == "array_object" and not kept:
                reject_reason = "array_object_without_sub_fields"
                _log_rejection(field, reject_reason)
                continue

        valid.append(field)

    return valid
