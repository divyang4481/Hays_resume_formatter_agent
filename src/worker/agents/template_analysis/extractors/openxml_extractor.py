from __future__ import annotations

from io import BytesIO
import re
from zipfile import ZipFile
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
TOKEN_RE = re.compile(r"\[[^\]]+\]|\"[^\"]+\"")
MERGE_RE = re.compile(r"MERGEFIELD\s+([^\s\\]+)", re.IGNORECASE)


def extract_openxml_evidence(docx_bytes: bytes) -> dict:
    from src.worker.agents.template_analysis.layout_extractor import _extract_from_xml_fields
    layout = _extract_from_xml_fields(docx_bytes)
    blocks = []
    for i, b in enumerate(layout.get("blocks", []), start=1):
        b = dict(b)
        b["source"] = "openxml"
        b["block_id"] = f"ox_b{i:03d}"
        # Set mergefield_name if token represents a MERGEFIELD
        tok = b.get("raw_token") or ""
        if tok.startswith("MERGEFIELD "):
            b["mergefield_name"] = tok.replace("MERGEFIELD ", "").strip()
        blocks.append(b)
    return {"source": "openxml", "blocks": blocks, "warnings": []}
