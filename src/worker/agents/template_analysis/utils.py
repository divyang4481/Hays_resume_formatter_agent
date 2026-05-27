from __future__ import annotations

from io import BytesIO
from docx import Document

def _extract_template_tokens(docx_bytes: bytes) -> list:
    from src.worker.agents.template_analysis.layout_extractor import (
        extract_layout_blocks_from_docx,
    )
    layout = extract_layout_blocks_from_docx(docx_bytes)
    return [
        (b.get("label_text") or "", b.get("raw_token") or "")
        for b in layout.get("blocks", [])
    ]


def _extract_template_text(docx_bytes: bytes) -> str:
    doc = Document(BytesIO(docx_bytes))
    return "\n".join(p.text for p in doc.paragraphs)


def _field_has_evidence(field: dict, template_text: str, token_values: set) -> bool:
    token = field.get("template_token", "")
    return token.lower() in template_text or token in token_values


def _clean_slug(s: str) -> str:
    import re
    text = (s or "").strip().strip('"').strip("'").strip('[').strip(']')
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    return text or "unknown_field"


def _build_grouped_section_fields(blocks: list) -> list:
    # Group blocks by section_heading
    sections = {}
    for b in blocks:
        heading = (b.get("section_heading") or "").strip()
        if not heading:
            continue
        sections.setdefault(heading, []).append(b)
        
    fields = []
    for heading, s_blocks in sorted(sections.items()):
        # Only group if there are multiple placeholder blocks in this section
        ph_blocks = [b for b in s_blocks if b.get("placeholder_text")]
        if len(ph_blocks) < 2:
            continue
            
        sub_fields = []
        seen_names = set()
        for sb in ph_blocks:
            ph = sb["placeholder_text"]
            sub_name = _clean_slug(ph)
            if sub_name.startswith("bullet_point_"):
                candidate = sub_name.replace("bullet_point_", "")
                if candidate:
                    sub_name = candidate
            # Prevent duplicate sub-fields in the same group
            if sub_name in seen_names:
                continue
            seen_names.add(sub_name)
            sub_fields.append({
                "name": sub_name,
                "field_type": "scalar",
                "template_token": ph,
            })
            
        fields.append({
            "name": _clean_slug(heading),
            "field_type": "array_object",
            "sub_fields": sub_fields,
            "template_token": ph_blocks[0]["placeholder_text"],
        })
        
    return fields
