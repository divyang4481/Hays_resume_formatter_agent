from __future__ import annotations

import re


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", (s or "").strip()).strip("_").lower() or "field"


def build_field_candidates_from_evidence(layout: dict) -> list[dict]:
    out = []
    for i, b in enumerate(layout.get("canonical_blocks", []), start=1):
        label = b.get("label_text") or b.get("section_heading") or b.get("raw_token")
        token = b.get("raw_token") or b.get("placeholder_text") or ""
        out.append({
            "candidate_id": f"fc{i:03d}", "suggested_name": _slug(label), "display_label": label, "field_type": "array" if b.get("is_bullet") else "scalar",
            "source_block_ids": [b.get("block_id")], "template_token": token,
            "template_evidence": {"section_heading": b.get("section_heading"), "label_text": b.get("label_text"), "placeholder_text": b.get("placeholder_text")},
            "render_contract": {"render_strategy": "mergefield_replace" if str(token).upper().startswith("MERGEFIELD") else "placeholder_replace", "anchor_token": token,
            "occurrence_selector": {"source_block_id": b.get("block_id"), "label_text": b.get("label_text"), "occurrence_key": b.get("occurrence_key")}},
        })
    return out
