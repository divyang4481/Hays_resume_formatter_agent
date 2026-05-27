from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", (s or "").strip()).strip("_").lower() or "field"


def _infer_field_type(block: dict[str, Any]) -> str:
    token = str(block.get("raw_token") or block.get("placeholder_text") or "").lower()
    if block.get("is_bullet") or "bullet" in token or "list" in token:
        return "array"
    return "scalar"


def _infer_render_strategy(token: str, field_type: str) -> str:
    if str(token).upper().startswith("MERGEFIELD"):
        return "mergefield_replace"
    if field_type == "array":
        return "bullet_list_replace"
    return "placeholder_replace"


def build_field_candidates_from_evidence(layout: dict) -> list[dict]:
    """Build raw evidence candidates, preserving one-per-block traceability.

    This stage intentionally stays block-level; logical grouping happens downstream.
    """
    blocks = layout.get("canonical_blocks", [])
    out = []
    by_section: dict[str, list[dict]] = defaultdict(list)

    for i, block in enumerate(blocks, start=1):
        label = block.get("label_text") or block.get("section_heading") or block.get("raw_token") or ""
        token = block.get("raw_token") or block.get("placeholder_text") or ""
        field_type = _infer_field_type(block)
        candidate = {
            "candidate_id": f"fc{i:03d}",
            "suggested_name": _slug(label),
            "display_label": label,
            "field_type": field_type,
            "source_block_ids": [block.get("block_id")],
            "template_token": token,
            "template_evidence": {
                "section_heading": block.get("section_heading"),
                "label_text": block.get("label_text"),
                "placeholder_text": block.get("placeholder_text"),
                "evidence_text": block.get("evidence_text"),
            },
            "render_contract": {
                "render_strategy": _infer_render_strategy(token, field_type),
                "anchor_token": token,
                "occurrence_selector": {
                    "source_block_id": block.get("block_id"),
                    "label_text": block.get("label_text"),
                    "section_heading": block.get("section_heading"),
                    "occurrence_key": block.get("occurrence_key"),
                },
            },
        }
        out.append(candidate)
        by_section[(block.get("section_heading") or "").strip().lower()].append(candidate)

    # annotate section context for later grouping/critic
    for section, items in by_section.items():
        section_size = len(items)
        for item in items:
            item.setdefault("template_evidence", {})["section_size"] = section_size
            item["template_evidence"]["section_key"] = section

    return out
