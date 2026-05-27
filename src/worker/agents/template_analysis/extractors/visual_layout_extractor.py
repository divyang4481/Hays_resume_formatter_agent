from __future__ import annotations


def extract_visual_layout_evidence(docx_bytes: bytes, filename: str = "template.docx") -> dict:
    return {"source": "visual", "blocks": [], "warnings": ["visual_layout_not_enabled"]}
